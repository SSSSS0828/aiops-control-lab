// Package aiopspluginsdk_test 验证插件清单的严格字段和安全路径边界。
package aiopspluginsdk_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	sdk "github.com/aiops-lab/aiops-plugin-sdk-go"
)

func TestLoadManifest(t *testing.T) {
	path := filepath.Join(t.TempDir(), "plugin.yaml")
	content := `
id: go-example
name: Go 示例插件
version: 0.1.0
api_version: v1
entrypoint: go-example
checksum: sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
capabilities: [Analyzer]
permissions: [network.http.outbound]
config_schema:
  type: object
`
	if err := os.WriteFile(path, []byte(content), 0o600); err != nil {
		t.Fatalf("写入测试清单失败: %v", err)
	}
	manifest, err := sdk.LoadManifest(path)
	if err != nil {
		t.Fatalf("合法清单不应失败: %v", err)
	}
	if manifest.ID != "go-example" || manifest.ConfigSchema["type"] != "object" {
		t.Fatalf("清单字段解析错误: %+v", manifest)
	}
}

func TestManifestRejectsParentEntrypoint(t *testing.T) {
	manifest := sdk.Manifest{
		ID:           "go-example",
		Name:         "Go 示例插件",
		Version:      "0.1.0",
		APIVersion:   "v1",
		Entrypoint:   "../outside",
		Checksum:     "sha256:" + strings.Repeat("a", 64),
		Capabilities: []string{"Analyzer"},
	}
	if err := manifest.Validate(); err == nil {
		t.Fatal("包含上级跳转的入口必须被拒绝")
	}
}
