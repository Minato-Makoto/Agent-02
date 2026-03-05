package security

import (
	"crypto/ed25519"
	"crypto/hmac"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"fmt"
	"strings"
)

func VerifyMetaSignature(body []byte, appSecret string, header string) bool {
	if appSecret == "" {
		return true
	}
	const prefix = "sha256="
	if !strings.HasPrefix(header, prefix) {
		return false
	}
	expected := strings.TrimPrefix(header, prefix)
	mac := hmac.New(sha256.New, []byte(appSecret))
	mac.Write(body)
	sum := hex.EncodeToString(mac.Sum(nil))
	return subtle.ConstantTimeCompare([]byte(sum), []byte(expected)) == 1
}

func VerifyDiscordSignature(publicKeyHex, signatureHex, timestamp string, body []byte) error {
	pk, err := hex.DecodeString(publicKeyHex)
	if err != nil {
		return fmt.Errorf("decode public key: %w", err)
	}
	sig, err := hex.DecodeString(signatureHex)
	if err != nil {
		return fmt.Errorf("decode signature: %w", err)
	}
	message := append([]byte(timestamp), body...)
	if !ed25519.Verify(ed25519.PublicKey(pk), message, sig) {
		return fmt.Errorf("invalid discord signature")
	}
	return nil
}