package api

import (
	"context"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/gofiber/fiber/v2/middleware/cors"
	"github.com/gofiber/fiber/v2/middleware/limiter"
	"github.com/gofiber/fiber/v2/middleware/recover"
	"github.com/gofiber/fiber/v2/middleware/requestid"
	"github.com/yourname/agent-02/src/adapters"
	"github.com/yourname/agent-02/src/gateway"
	"github.com/yourname/agent-02/src/security"
	"github.com/yourname/agent-02/src/store"
)

type Server struct {
	runtime   *gateway.Runtime
	adminToken string
	masterKey []byte
}

type chatRequest struct {
	Platform  string `json:"platform"`
	ChannelID string `json:"channel_id"`
	UserID    string `json:"user_id"`
	Message   string `json:"message"`
}

type denyRequest struct {
	Reason string `json:"reason"`
}

type skillToggleRequest struct {
	Skill   string `json:"skill"`
	Enabled bool   `json:"enabled"`
}

func NewServer(runtime *gateway.Runtime, masterKey []byte) (*Server, error) {
	adminToken, err := security.DecryptString(masterKey, runtime.Config.Security.AdminTokenEnc)
	if err != nil {
		return nil, err
	}
	return &Server{runtime: runtime, masterKey: masterKey, adminToken: adminToken}, nil
}

func (s *Server) Listen(ctx context.Context) error {
	cfg := s.runtime.Config.Server

	app := fiber.New(fiber.Config{
		AppName:               "Agent-02 Secure Gateway",
		DisableStartupMessage: true,
		ReadTimeout:           time.Duration(cfg.ReadTimeoutSec) * time.Second,
		WriteTimeout:          time.Duration(cfg.WriteTimeoutSec) * time.Second,
		IdleTimeout:           time.Duration(cfg.IdleTimeoutSec) * time.Second,
		BodyLimit:             cfg.RequestBodyLimit,
		EnablePrintRoutes:     false,
	})

	app.Use(recover.New())
	app.Use(requestid.New())
	app.Use(cors.New(cors.Config{
		AllowOrigins:     "http://localhost:8080,http://127.0.0.1:8080,tauri://localhost",
		AllowHeaders:     "Origin, Content-Type, Accept, X-Agent02-Token",
		AllowMethods:     "GET,POST,OPTIONS",
		AllowCredentials: false,
	}))
	app.Use(limiter.New(limiter.Config{
		Max:        120,
		Expiration: 1 * time.Minute,
	}))
	app.Use(s.securityHeaders)

	s.registerUI(app)
	s.registerAPIRoutes(app)
	s.registerWebhookRoutes(app)

	addr := net.JoinHostPort(cfg.Host, fmt.Sprintf("%d", cfg.Port))
	go func() {
		<-ctx.Done()
		_ = app.Shutdown()
	}()
	return app.Listen(addr)
}

func (s *Server) registerAPIRoutes(app *fiber.App) {
	api := app.Group("/api")
	api.Get("/status", func(c *fiber.Ctx) error {
		return c.JSON(fiber.Map{
			"ok": true,
			"server": fiber.Map{
				"host": s.runtime.Config.Server.Host,
				"port": s.runtime.Config.Server.Port,
			},
			"connectors": fiber.Map{
				"telegram": s.runtime.Telegram != nil,
				"whatsapp": s.runtime.WhatsApp != nil,
				"discord":  s.runtime.Discord != nil,
			},
			"llm": fiber.Map{
				"provider": s.runtime.Config.LLM.Provider,
				"model":    s.runtime.Config.LLM.Model,
			},
		})
	})

	api.Use(s.adminAuth)

	api.Post("/chat", func(c *fiber.Ctx) error {
		var req chatRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": err.Error()})
		}
		msg := adapters.InboundMessage{
			Platform:  req.Platform,
			ChannelID: req.ChannelID,
			UserID:    req.UserID,
			Text:      req.Message,
		}
		if msg.Platform == "" {
			msg.Platform = "ui"
		}
		if msg.ChannelID == "" {
			msg.ChannelID = "ui"
		}
		if msg.UserID == "" {
			msg.UserID = "local-user"
		}
		resp, err := s.runtime.Service.ProcessInbound(c.UserContext(), msg)
		if err != nil {
			return c.Status(fiber.StatusBadGateway).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(fiber.Map{"reply": resp})
	})

	api.Get("/consents", func(c *fiber.Ctx) error {
		items, err := s.runtime.Service.ListPendingConsents(100)
		if err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(fiber.Map{"items": items})
	})

	api.Post("/consents/:id/approve", func(c *fiber.Ctx) error {
		res, err := s.runtime.Service.ApproveConsent(c.UserContext(), c.Params("id"))
		if err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(res)
	})

	api.Post("/consents/:id/deny", func(c *fiber.Ctx) error {
		var req denyRequest
		_ = c.BodyParser(&req)
		if err := s.runtime.Service.DenyConsent(c.Params("id"), req.Reason); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(fiber.Map{"ok": true})
	})

	api.Get("/notes", func(c *fiber.Ctx) error {
		notes, err := s.runtime.Service.ListNotes(50)
		if err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(fiber.Map{"items": notes})
	})

	api.Post("/skills/enable", func(c *fiber.Ctx) error {
		var req skillToggleRequest
		if err := c.BodyParser(&req); err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": err.Error()})
		}
		req.Skill = strings.ToLower(strings.TrimSpace(req.Skill))
		if req.Skill == "" {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"error": "skill is required"})
		}
		s.runtime.Config.Skills.Enabled[req.Skill] = req.Enabled
		if err := store.SaveConfig(s.runtime.DataDir, s.runtime.Config); err != nil {
			return c.Status(fiber.StatusInternalServerError).JSON(fiber.Map{"error": err.Error()})
		}
		return c.JSON(fiber.Map{"ok": true, "skill": req.Skill, "enabled": req.Enabled})
	})

	api.Post("/connect/:platform/test", func(c *fiber.Ctx) error {
		ctx, cancel := context.WithTimeout(c.UserContext(), 10*time.Second)
		defer cancel()
		platform := strings.ToLower(c.Params("platform"))
		var err error
		switch platform {
		case "telegram":
			if s.runtime.Telegram == nil {
				err = fmt.Errorf("telegram is not configured")
			} else {
				err = s.runtime.Telegram.SelfTest(ctx)
			}
		case "whatsapp":
			if s.runtime.WhatsApp == nil {
				err = fmt.Errorf("whatsapp is not configured")
			} else {
				err = s.runtime.WhatsApp.SelfTest(ctx)
			}
		case "discord":
			if s.runtime.Discord == nil {
				err = fmt.Errorf("discord is not configured")
			} else {
				err = s.runtime.Discord.SelfTest(ctx)
			}
		default:
			err = fmt.Errorf("unsupported platform: %s", platform)
		}
		if err != nil {
			return c.Status(fiber.StatusBadRequest).JSON(fiber.Map{"ok": false, "error": err.Error()})
		}
		return c.JSON(fiber.Map{"ok": true})
	})
}

func (s *Server) registerWebhookRoutes(app *fiber.App) {
	if s.runtime.Telegram != nil {
		app.Post(s.runtime.Config.Connectors.Telegram.WebhookPath, func(c *fiber.Ctx) error {
			msg, err := s.runtime.Telegram.ParseWebhook(c)
			if err != nil {
				if err == fiber.ErrNoContent {
					return c.SendStatus(fiber.StatusOK)
				}
				if err == fiber.ErrUnauthorized {
					return c.SendStatus(fiber.StatusUnauthorized)
				}
				return c.Status(fiber.StatusBadRequest).SendString(err.Error())
			}
			resp, err := s.runtime.Service.ProcessInbound(c.UserContext(), msg)
			if err == nil && strings.TrimSpace(resp) != "" {
				_ = s.runtime.Telegram.SendText(c.UserContext(), msg.ChannelID, resp)
			}
			return c.SendStatus(fiber.StatusOK)
		})
	}

	if s.runtime.WhatsApp != nil {
		app.Get(s.runtime.Config.Connectors.WhatsApp.WebhookPath, s.runtime.WhatsApp.VerifyWebhook)
		app.Post(s.runtime.Config.Connectors.WhatsApp.WebhookPath, func(c *fiber.Ctx) error {
			msg, err := s.runtime.WhatsApp.ParseWebhook(c)
			if err != nil {
				if err == fiber.ErrNoContent {
					return c.SendStatus(fiber.StatusOK)
				}
				if err == fiber.ErrUnauthorized {
					return c.SendStatus(fiber.StatusUnauthorized)
				}
				return c.Status(fiber.StatusBadRequest).SendString(err.Error())
			}
			resp, err := s.runtime.Service.ProcessInbound(c.UserContext(), msg)
			if err == nil && strings.TrimSpace(resp) != "" {
				_ = s.runtime.WhatsApp.SendText(c.UserContext(), msg.ChannelID, resp)
			}
			return c.SendStatus(fiber.StatusOK)
		})
	}

	if s.runtime.Discord != nil {
		app.Post(s.runtime.Config.Connectors.Discord.WebhookPath, func(c *fiber.Ctx) error {
			msg, interactionType, err := s.runtime.Discord.ParseInteraction(c)
			if err != nil {
				if err == fiber.ErrNoContent {
					return c.SendStatus(fiber.StatusOK)
				}
				if err == fiber.ErrUnauthorized {
					return c.SendStatus(fiber.StatusUnauthorized)
				}
				return c.Status(fiber.StatusBadRequest).SendString(err.Error())
			}
			if interactionType == 1 {
				return s.runtime.Discord.InteractionPong(c)
			}
			resp, err := s.runtime.Service.ProcessInbound(c.UserContext(), msg)
			if err != nil {
				resp = "Gateway error: " + err.Error()
			}
			return s.runtime.Discord.InteractionMessage(c, resp)
		})
	}
}

func (s *Server) registerUI(app *fiber.App) {
	dist := filepath.Join("ui", "dist")
	if stat, err := os.Stat(dist); err == nil && stat.IsDir() {
		app.Static("/", dist)
		return
	}
	app.Get("/", func(c *fiber.Ctx) error {
		return c.Type("html").SendString(fallbackHTML)
	})
}

func (s *Server) adminAuth(c *fiber.Ctx) error {
	if !s.runtime.Config.Security.RequireAdminAuth {
		return c.Next()
	}
	if s.adminToken == "" {
		return c.Status(fiber.StatusForbidden).JSON(fiber.Map{"error": "admin token is not configured"})
	}
	token := c.Get("X-Agent02-Token")
	if token != s.adminToken {
		return c.Status(fiber.StatusUnauthorized).JSON(fiber.Map{"error": "invalid admin token"})
	}
	return c.Next()
}

func (s *Server) securityHeaders(c *fiber.Ctx) error {
	c.Set("X-Content-Type-Options", "nosniff")
	c.Set("X-Frame-Options", "DENY")
	c.Set("Referrer-Policy", "no-referrer")
	c.Set("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
	c.Set("Content-Security-Policy", "default-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:8080 http://localhost:8080")
	return c.Next()
}

const fallbackHTML = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Agent-02 Control UI</title>
  <style>
    :root { --bg:#0e1627; --card:#111d34; --text:#f4f8ff; --muted:#9bb2d9; --accent:#2dd4bf; }
    body { margin:0; font-family: ui-sans-serif, system-ui; background:linear-gradient(140deg,#091122,#132c4f); color:var(--text); }
    .wrap { max-width: 880px; margin: 6rem auto; padding: 2rem; }
    .card { background:rgba(17,29,52,.9); border:1px solid rgba(118,163,230,.3); border-radius:16px; padding:1.5rem; }
    h1 { margin:0 0 .5rem; font-size:2rem; }
    p { color:var(--muted); line-height:1.6; }
    code { background:#0b1425; border-radius:6px; padding:.2rem .4rem; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h1>Agent-02 Control UI</h1>
      <p>UI bundle not found at <code>ui/dist</code>. Build desktop/web UI in <code>ui/</code> and refresh.</p>
      <p>Gateway API is available at <code>/api/status</code>.</p>
    </div>
  </div>
</body>
</html>`