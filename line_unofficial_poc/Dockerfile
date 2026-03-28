# Linux コンテナ用（Docker / Colima 等）。macOS ネイティブは setup_phase_b_mac.sh を使う。
#
#   docker build -t line-chrline-poc .
#   docker run --rm -it -v "$PWD:/wrk" -w /wrk line-chrline-poc bash

FROM python:3.11-slim-bookworm

WORKDIR /wrk

COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir "CHRLINE==2.5.14"

RUN python -c "import CHRLINE; print('CHRLINE import OK')"

CMD ["python", "-c", "print('line_unofficial_poc: docker OK。bash で対話してください。')"]
