package skills

import (
	"path/filepath"
	"strings"
)

type Policy struct {
	AllowedRoots []string
}

func (p Policy) IsPathAllowed(candidate string) bool {
	if len(p.AllowedRoots) == 0 {
		return false
	}
	clean := filepath.Clean(candidate)
	for _, root := range p.AllowedRoots {
		r := filepath.Clean(root)
		rel, err := filepath.Rel(r, clean)
		if err != nil {
			continue
		}
		if rel == "." || (rel != ".." && !strings.HasPrefix(rel, ".."+string(filepath.Separator))) {
			return true
		}
	}
	return false
}
