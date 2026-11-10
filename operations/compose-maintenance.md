# Compose maintenance

Normal deployment pulls missing images and starts the desired stack. It does
not remove networks or images. Retain the previous configuration and image for
rollback; registry availability must not be the only rollback path.

Run `just prune-images <inventory-host>` separately after reviewing unused images
on that host and confirming rollback needs. The recipe removes unused images
created more than 30 days ago, including tagged images. Image creation age is
not time since last use: an old previous-release image may still be removed.
The recipe leaves containers, volumes, networks and build cache alone. Do not use
an inventory group when intending to maintain one host.

The former implicit-network cleanup was a one-time migration operation. Inspect
network attachments before removing any leftover network manually; failures
should be investigated rather than suppressed during every deployment.
