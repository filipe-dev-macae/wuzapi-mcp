FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml requirements.lock LICENSE ./
COPY aguaviva ./aguaviva
RUN pip install --no-cache-dir -r requirements.lock && pip install --no-cache-dir --no-deps . && useradd --uid 10001 --create-home attendance && mkdir /data && chown attendance /data
USER attendance
ENV ATTENDANCE_MODELS=/data/models
ENTRYPOINT ["aguaviva-attendance"]
CMD ["--config", "/config/config.json", "--data", "/data"]
