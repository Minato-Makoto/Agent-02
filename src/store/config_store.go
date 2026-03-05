package store

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"

	"github.com/yourname/agent-02/src/config"
)

const configFileName = "config.json"

func ConfigPath(dataDir string) string {
	return filepath.Join(dataDir, configFileName)
}

func LoadConfig(dataDir string) (config.AppConfig, error) {
	_ = os.MkdirAll(dataDir, 0o700)
	path := ConfigPath(dataDir)
	if _, err := os.Stat(path); os.IsNotExist(err) {
		cfg := config.DefaultConfig(dataDir)
		if err := SaveConfig(dataDir, cfg); err != nil {
			return config.AppConfig{}, err
		}
		return cfg, nil
	}

	b, err := os.ReadFile(path)
	if err != nil {
		return config.AppConfig{}, err
	}

	var cfg config.AppConfig
	if err := json.Unmarshal(b, &cfg); err != nil {
		return config.AppConfig{}, fmt.Errorf("parse %s: %w", path, err)
	}
	return cfg, nil
}

func SaveConfig(dataDir string, cfg config.AppConfig) error {
	_ = os.MkdirAll(dataDir, 0o700)
	path := ConfigPath(dataDir)
	b, err := json.MarshalIndent(cfg, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(path, b, 0o600)
}