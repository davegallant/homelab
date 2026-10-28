# Intel GPU device plugin

This plugin is scoped to `k8s-w-1` and `k8s-w-2` and exposes their passed-through
Intel GPUs as Kubernetes resources. The namespace has a privileged Pod Security
exception because the plugin needs host device, sysfs, and kubelet socket
paths. The plugin drops all capabilities and does not run privileged.

Each host GPU is dedicated to its worker. The worker Talos images must include
`siderolabs/i915` for the installed Talos version. Verify the device and node
allocatable resource before scheduling a GPU workload. Namespace, plugin and host configuration
must remain in place while workloads request the resource.
