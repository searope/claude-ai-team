FROM python:3.12-slim

# Every setting of src/orders/settings.py gets its value here; tools/check_infra.py checks that.
ENV ORDERS_PORT=8000
ENV PYTHONPATH=/app/src

WORKDIR /app
COPY src/ ./src/

RUN useradd --create-home --uid 10001 orders
USER orders

EXPOSE 8000
CMD ["python", "-m", "orders.server"]
