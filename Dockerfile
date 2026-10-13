FROM python:3.12-slim@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1
WORKDIR /srv
COPY app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home lab
COPY app /srv/app
COPY policies /srv/policies
USER 10001
EXPOSE 8080
CMD ["python", "-m", "app.server"]
