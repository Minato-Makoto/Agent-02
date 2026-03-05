package security

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"io"
	"os"
	"path/filepath"
)

const masterKeyFile = "master.key"

func LoadOrCreateMasterKey(dataDir string) ([]byte, error) {
	if envKey := os.Getenv("AGENT02_MASTER_KEY"); envKey != "" {
		if decoded, err := base64.StdEncoding.DecodeString(envKey); err == nil && len(decoded) == 32 {
			return decoded, nil
		}
		sum := sha256.Sum256([]byte(envKey))
		return sum[:], nil
	}

	keyPath := filepath.Join(dataDir, masterKeyFile)
	if b, err := os.ReadFile(keyPath); err == nil {
		if len(b) != 32 {
			return nil, fmt.Errorf("invalid key length in %s", keyPath)
		}
		return b, nil
	}

	key := make([]byte, 32)
	if _, err := io.ReadFull(rand.Reader, key); err != nil {
		return nil, err
	}

	if err := os.WriteFile(keyPath, key, 0o600); err != nil {
		return nil, err
	}

	return key, nil
}

func EncryptString(key []byte, plaintext string) (string, error) {
	if plaintext == "" {
		return "", nil
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, gcm.NonceSize())
	if _, err := io.ReadFull(rand.Reader, nonce); err != nil {
		return "", err
	}
	ciphertext := gcm.Seal(nonce, nonce, []byte(plaintext), nil)
	return base64.StdEncoding.EncodeToString(ciphertext), nil
}

func DecryptString(key []byte, encoded string) (string, error) {
	if encoded == "" {
		return "", nil
	}
	payload, err := base64.StdEncoding.DecodeString(encoded)
	if err != nil {
		return "", err
	}
	block, err := aes.NewCipher(key)
	if err != nil {
		return "", err
	}
	gcm, err := cipher.NewGCM(block)
	if err != nil {
		return "", err
	}
	if len(payload) < gcm.NonceSize() {
		return "", errors.New("invalid ciphertext")
	}
	nonce := payload[:gcm.NonceSize()]
	ciphertext := payload[gcm.NonceSize():]
	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", err
	}
	return string(plaintext), nil
}