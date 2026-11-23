# Backup/restore tool: pg_dump + tar, encrypted with age, optional off-site copy with rclone.
# The server only needs Docker; nothing is installed on the host.
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf
RUN apk add --no-cache age postgresql16-client rclone tar gzip coreutils \
    && addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /home/app app
COPY --chmod=0755 backup.sh restore.sh /usr/local/bin/
USER app
ENTRYPOINT ["/usr/local/bin/backup.sh"]
