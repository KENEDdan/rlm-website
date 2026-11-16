# Backup/restore tool: pg_dump + tar, encrypted with age, optional off-site copy with rclone.
# The server only needs Docker; nothing is installed on the host.
FROM alpine:3.20@sha256:d9e853e87e55526f6b2917df91a2115c36dd7c696a35be12163d44e6e2a4b6bc
RUN apk add --no-cache age postgresql16-client rclone tar gzip coreutils \
    && addgroup -S -g 10001 app && adduser -S -u 10001 -G app -h /home/app app
COPY --chmod=0755 backup.sh restore.sh /usr/local/bin/
USER app
ENTRYPOINT ["/usr/local/bin/backup.sh"]
