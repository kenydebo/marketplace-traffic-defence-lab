FROM python:3.12-slim
WORKDIR /srv
COPY app/requirements.txt /srv/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt && useradd --uid 10001 --create-home lab
COPY app /srv/app
COPY policies /srv/policies
USER 10001
EXPOSE 8080
CMD ["python", "-m", "app.server"]
