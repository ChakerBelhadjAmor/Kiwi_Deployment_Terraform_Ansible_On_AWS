#!/bin/sh
# Print the current digest of every pinned image, in vars.yml form.
# Needs skopeo. Anonymous pulls are rate limited by Docker Hub; retry later if it says "toomanyrequests".
set -eu
d() { skopeo inspect --no-tags --format '{{.Digest}}' "docker://$1"; }
echo "kiwi_image_tag:    \"latest@$(d docker.io/kiwitcms/kiwitcms:latest)\"   # same repo as pub.kiwitcms.eu"
echo "mariadb_image_tag: \"11.8@$(d docker.io/library/mariadb:11.8)\""
echo "caddy_image_tag:   \"2.11-alpine@$(d docker.io/library/caddy:2.11-alpine)\""
