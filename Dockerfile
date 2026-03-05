FROM golang:1.25-alpine AS build
WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY cmd ./cmd
COPY src ./src

RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/agent02 ./cmd/agent02

FROM gcr.io/distroless/static-debian12:nonroot
WORKDIR /app
COPY --from=build /out/agent02 /usr/local/bin/agent02
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/agent02"]
CMD ["start", "--data-dir", "/app/data"]