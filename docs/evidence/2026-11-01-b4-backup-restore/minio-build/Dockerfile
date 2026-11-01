FROM golang:1.24.8-alpine3.22 AS build
ENV CGO_ENABLED=0 GOMAXPROCS=4 GOTOOLCHAIN=local
WORKDIR /build
COPY source/go.mod source/go.sum ./
RUN go mod download
COPY source/ ./
RUN go build -mod=readonly -p 4 -trimpath -ldflags='-s -w -X github.com/minio/minio/cmd.Version=2025-10-15T17:29:55Z -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-10-15T17-29-55Z -X github.com/minio/minio/cmd.CommitID=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a -X github.com/minio/minio/cmd.ShortCommitID=9e49d5e7a648' -o /out/minio .

FROM alpine:3.22
RUN apk add --no-cache ca-certificates curl && addgroup -g 10001 minio && adduser -D -u 10001 -G minio minio && mkdir /data && chown minio:minio /data
COPY --from=build /out/minio /usr/local/bin/minio
LABEL org.opencontainers.image.source="https://github.com/minio/minio" org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a"
USER 10001:10001
EXPOSE 9000 9001
HEALTHCHECK --interval=10s --timeout=3s --start-period=15s CMD curl --fail --silent http://127.0.0.1:9000/minio/health/live || exit 1
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--address", ":9000", "--console-address", ":9001"]
