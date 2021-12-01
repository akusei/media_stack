#!/bin/bash

# this is old and should not be used

docker run -d \
        -v /etc/timezone:/etc/timezone:ro \
        -v /etc/localtime:/etc/localtime:ro \
        -v ${CACHE_PATH}:/config \
        -v ${TRANSCODE_PATH}:/transcode \
        -v ${MEDIA_ROOT}:/data:ro \
        -v /dev/dri:/dev/dri \
        -p 32400:32400/tcp \
        -p 3005:3005/tcp \
        -p 8324:8324/tcp \
        -p 32469:32469/tcp \
        -p 1900:1900/udp \
        -p 32410:32410/udp \
        -p 32412:32412/udp \
        -p 32413:32413/udp \
        -p 32414:32414/udp \
        --expose 32400 \
        --expose 3005 \
        --expose 8324 \
        --expose 32469 \
        --expose 1900 \
        --expose 32410 \
        --expose 32412 \
        --expose 32413 \
        --expose 32414 \
        --name=plex \
        --restart=unless-stopped \
        --gpus=all \
        -e NVIDIA_VISIBLE_DEVICES=all \
        -e NVIDIA_DRIVER_CAPABILITIES=all \
        -e ALLOWED_NETWORKS=${ALLOWED_NETWORKS:-} \
        -e ADVERTISE_IP=${ADVERTISE_IP} \
        -e PLEX_UID=${PLEX_UID} \
        -e PLEX_GID=${PLEX_GID} \
        -e CHANGE_CONFIG_DIR_OWNERSHIP="false" \
        -e PLEX_CLAIM="" \
        --privileged \
        --device /dev/dri/card0 \
        --device /dev/dri/renderD128 \
        --network traefik \
        --label "traefik.enable=true" \
        --label "traefik.http.routers.plex.service=plex" \
        --label "traefik.http.routers.plex.rule=Host(\`${DOMAIN}\`)" \
        --label "traefik.http.routers.plex.entrypoints=https" \
        --label "traefik.http.routers.plex.tls=true" \
        --label "traefik.http.services.plex.loadbalancer.server.port=32400" \
        plexinc/pms-docker:plexpass
