// Package aiopspluginsdk 提供独立进程插件的 Go 服务端与清单校验能力。
package aiopspluginsdk

import (
	"errors"
	"fmt"
	"os"
	"regexp"
	"strings"

	"gopkg.in/yaml.v3"
)

var pluginIDPattern = regexp.MustCompile(`^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$`)

// Manifest 对应 plugin.yaml 中跨语言稳定的公开字段。
type Manifest struct {
	ID           string         `yaml:"id"`
	Name         string         `yaml:"name"`
	Version      string         `yaml:"version"`
	APIVersion   string         `yaml:"api_version"`
	Entrypoint   string         `yaml:"entrypoint"`
	Checksum     string         `yaml:"checksum"`
	Capabilities []string       `yaml:"capabilities"`
	Permissions  []string       `yaml:"permissions"`
	ConfigSchema map[string]any `yaml:"config_schema,omitempty"`
}

// LoadManifest 严格解析清单并执行不依赖部署环境的格式校验。
func LoadManifest(path string) (Manifest, error) {
	content, err := os.ReadFile(path)
	if err != nil {
		return Manifest{}, fmt.Errorf("读取插件清单失败: %w", err)
	}
	var manifest Manifest
	decoder := yaml.NewDecoder(strings.NewReader(string(content)))
	decoder.KnownFields(true)
	if err := decoder.Decode(&manifest); err != nil {
		return Manifest{}, fmt.Errorf("解析插件清单失败: %w", err)
	}
	if err := manifest.Validate(); err != nil {
		return Manifest{}, err
	}
	return manifest, nil
}

// Validate 检查插件作者可以独立确定的清单不变量。
func (m Manifest) Validate() error {
	if !pluginIDPattern.MatchString(m.ID) {
		return errors.New("插件 ID 必须是 3 到 64 位小写字母、数字或连字符")
	}
	if strings.TrimSpace(m.Name) == "" || strings.TrimSpace(m.Version) == "" {
		return errors.New("插件名称和版本不能为空")
	}
	if m.APIVersion != "v1" {
		return fmt.Errorf("不支持插件 API %q", m.APIVersion)
	}
	if strings.Contains(m.Entrypoint, "..") || strings.TrimSpace(m.Entrypoint) == "" {
		return errors.New("插件入口必须是包内相对路径且不能包含上级跳转")
	}
	if !regexp.MustCompile(`^sha256:[a-f0-9]{64}$`).MatchString(m.Checksum) {
		return errors.New("插件校验和必须是完整 sha256 十六进制值")
	}
	if len(m.Capabilities) == 0 {
		return errors.New("插件至少需要声明一项能力")
	}
	return nil
}
