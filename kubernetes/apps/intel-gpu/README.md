# Intel GPU device plugin

This plugin is scoped to `k8s-w-2` and exposes its passed-through Intel
GPU as a Kubernetes resource. The namespace has a privileged Pod Security
exception because the plugin needs host device, sysfs, and kubelet socket
paths. The plugin drops all capabilities and does not run privileged.

The host GPU is dedicated to the worker; Jellyfin uses the separate GPU on
`pve-g3-1`. The `k8s-w-2` Talos image must include `siderolabs/i915` for
the installed Talos version. Verify the device and node allocatable resource
before scheduling a GPU workload. Namespace, plugin and host configuration
must remain in place while workloads request the resource.
