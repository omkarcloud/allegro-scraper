FROM chetan1111/botasaurus:chrome-151

ENV PYTHONUNBUFFERED=1
# Never open debug prompts/devtools on crash.
ENV ENV=production

COPY requirements.txt .

RUN python -m pip install --no-cache-dir -r requirements.txt

RUN mkdir app
WORKDIR /app
COPY . /app

EXPOSE 8000

# The image ships real Google Chrome + Xvfb. Chrome only starts to pass
# DataDome once per marketplace (through ALLEGRO_PROXY); every request after
# that runs over plain HTTP with the cookie it earned.
CMD ["python", "run.py"]
