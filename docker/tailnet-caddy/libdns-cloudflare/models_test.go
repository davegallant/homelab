package cloudflare

import (
	"testing"

	"github.com/libdns/libdns"
)

func TestCloudflareRecordUsesRawTXTText(t *testing.T) {
	const token = "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"

	record, err := cloudflareRecord(libdns.TXT{
		Name: "_acme-challenge",
		Text: token,
	})
	if err != nil {
		t.Fatalf("cloudflareRecord() error = %v", err)
	}
	if record.Content != token {
		t.Fatalf("TXT content = %q, want raw token %q", record.Content, token)
	}
}
