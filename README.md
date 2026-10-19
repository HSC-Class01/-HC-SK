# SK(주) DART 재무 대시보드

[![🔗 대시보드 바로가기](https://img.shields.io/badge/🔗-대시보드%20바로가기-0b6bcb?style=for-the-badge)](https://hsc-class01.github.io/-HC-SK/)
[![🤖 에이전트 ZIP 다운로드](https://img.shields.io/badge/🤖-에이전트%20ZIP%20다운로드-08795c?style=for-the-badge)](https://github.com/HSC-Class01/-HC-SK/raw/refs/heads/main/downloads/SK_DART_Agent.zip)

SK(주)(유가증권시장 034730)의 DART 공시에서 재무 데이터를 수집해 연간·반기·분기 재무제표와 주요 비율을 계산하고 GitHub Pages 대시보드에 표시합니다.

## 시작하기

1. DART Open API에서 인증키를 발급합니다: <https://opendart.fss.or.kr/>
2. GitHub 저장소 **Settings → Secrets and variables → Actions → New repository secret**에서 이름을 `DART_API_KEY`, 값에 발급받은 인증키를 입력합니다. 키를 코드, 커밋, 이 ZIP 파일에 넣지 마세요.
3. **Settings → Pages**에서 **Build and deployment → Source: GitHub Actions**를 선택합니다.
4. **Actions → DART 재무 데이터 갱신 → Run workflow**를 눌러 첫 수집을 실행합니다. 매월 1일 10:00 KST에 자동 갱신됩니다.
5. 공개 대시보드: <https://hsc-class01.github.io/-HC-SK/>

워크플로가 데이터 파일을 갱신하고 Pages를 배포합니다. 인증키가 아직 없으면 데이터 수집 단계만 건너뛰고 안내 화면을 배포합니다.

## 데이터와 지표

- `data/financial_data.json`: DART 원천에서 정규화한 연결 재무제표, 기간·보고서 접수번호, 계산 비율과 갱신 시각
- `data/filings/`: 내려받은 사업보고서 원문 ZIP (GitHub 크기 제한을 넘는 파일은 저장하지 않고 공시 링크를 남김)
- `index.html`: 상단 재무 추이 그래프와 핵심 지표, 하단 연간·반기·분기별 데이터 테이블, 마지막 국내 peer firms 표
- `scripts/update_data.py`: DART 데이터 수집 및 비율 계산

비율은 공시된 연결 기준 숫자로 계산합니다. 유동비율=유동자산/유동부채, 부채비율=부채/자본, 자기자본비율=자본/자산, 영업이익률=영업이익/매출, 순이익률=순이익/매출, ROA=순이익/평균자산, ROE=순이익/평균자본, 총자산회전율=매출/평균자산입니다. 반기·분기 ROA·ROE·총자산회전율은 해당 보고 구간의 금액으로 계산하며 연환산하지 않습니다. 성장률은 같은 보고 구간의 전년 동기 대비로 표시하며 비교값이 없거나 전년도 영업이익이 0 이하이면 공란입니다. 3분기 손익은 DART API의 단독 분기 금액을 사용합니다. 재무비율은 공시 숫자를 기계적으로 계산한 참고 정보이며 투자 권유가 아닙니다.

## 로컬 실행

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DART_API_KEY = "발급받은_인증키"
python scripts/update_data.py
```

생성된 `data/financial_data.json`을 `index.html`이 읽습니다. 브라우저에서 로컬 파일로 열 때 fetch가 차단되면 `python -m http.server 8000` 실행 후 `http://localhost:8000`을 여세요.

## 국내 peer firms

아래 비교군은 SK(주) 기업가치 제고 계획에 명시된 국내 지주회사 peer를 바탕으로 구성했습니다. 기업마다 사업 포트폴리오와 연결·별도 재무 구조가 달라 단순 비교에 유의하세요.

| 회사 | 종목코드 | 비교 맥락 |
|---|---:|---|
| POSCO홀딩스 | 005490 | 사업형 지주회사 |
| 삼성물산 | 028260 | 사업형 지주회사 |
| LG | 003550 | 순수 지주회사 |
| LS | 006260 | 사업형 지주회사 |
| GS | 078930 | 순수 지주회사 |
| CJ | 001040 | 사업형 지주회사 |
| 두산 | 000150 | 사업형 지주회사 |
| 롯데지주 | 004990 | 순수 지주회사 |
| 한화 | 000880 | 사업형 지주회사 |

출처: [SK(주) 기업가치 제고 계획](https://www.sk-inc.com/kr/ir/irLibrary.aspx) (국내 지주회사 peer 명단). 분석대상 종목코드는 [SK 투자자 FAQ](https://sk-inc.com/kr/m/ir/faq.aspx) 및 DART 기준입니다.

## GitHub Pages / 자동화

GitHub Actions는 `schedule`로 매월 1일 01:00 UTC (한국시간 10:00)에 실행되며 수동 실행도 지원합니다. 첫 수집을 실행한 뒤 결과와 Actions 실행 로그를 확인하세요. GitHub의 예약 실행은 부하에 따라 지연될 수 있습니다.

