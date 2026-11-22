FROM python:3.13-slim@sha256:e48f59cdba69a3cbd9ed2cf0f348d90d45a8d350d98134cf1070bc106ee9ed90 AS prepare
COPY bundle.sh /tmp/bundle.sh
RUN /bin/sh /tmp/bundle.sh

FROM scratch
COPY --from=prepare /out/ /
