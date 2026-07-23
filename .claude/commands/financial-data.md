# 财务数据获取与交叉验证规范

本规范适用于所有涉及企业财务数据的研究。**每个关键数据必须来自两个独立来源，误差>1%须标记。**

---

## 数据源优先级

### 美股（PDD、腾讯ADR、网易ADR等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|---------|
| 1（主） | **macrotrends** | macrotrends.net/stocks/charts/{ticker} | 直接访问，无需注册 |
| 2（副） | **stockanalysis** | stockanalysis.com/stocks/{ticker}/financials | 直接访问，无需注册 |
| 原始一手 | SEC EDGAR | sec.gov/cgi-bin/browse-edgar | 10-K / 10-Q 原文 |

### 港股（腾讯0700、网易9999、美团3690等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|---------|
| 1（主） | **aastocks** | aastocks.com/tc/stocks/analysis/company-fundamental | 直接访问 |
| 2（副） | **macrotrends**（ADR代码） | 腾讯用TCEHY，网易用NTES | 直接访问 |
| 原始一手 | HKEX披露易 | hkexnews.hk | 年报PDF |

### A股（三七互娱、吉比特等）

| 优先级 | 来源 | URL | 获取方式 |
|--------|------|-----|---------|
| 1（主） | **东方财富** | eastmoney.com → 搜股票代码 → 财务报表 | 直接访问 |
| 2（副） | **巨潮资讯** | cninfo.com.cn | 原始年报/季报PDF |

### 한국주식 (KRX: 코스피·코스닥 — 삼성전자·LG이노텍 등)

| 우선순위 | 소스 | 접근 방식 |
|--------|------|---------|
| 1 (원문·주) | **DART 전자공시(FSS)** | MCP 도구 `mcp__dart__*` + `opendart-*`. 공식 공시 원문 = 최우선 정본 |
| 2 (시장데이터·보조) | **Yahoo Finance** | MCP `{종목코드}.KS`(코스피)/`.KQ`(코스닥). 주가·시총·PER·베타 (DART에 없는 시장지표) |
| 컨센서스 | 네이버페이 증권 / FnGuide | finance.naver.com — 목표가·추정치 |

**DART MCP 표준 호출 절차**:
1. **corp_code 확보** — `opendart-find_company`(query=기업명) → `corp_code`(8자리) + `stock_code`
2. **재무제표** — `mcp__dart__get_financial_summary`(corp_code, bsns_year, reprt_code, fs_div)
   - `reprt_code`: `11011`=사업보고서(연간·가장 상세) / `11012`=반기 / `11013`=1Q / `11014`=3Q
   - `fs_div`: `CFS`=연결(권장) / `OFS`=개별
   - 주의: 응답이 큼(약 90k자) → 도구가 자동으로 파일에 저장하면 `grep`으로 계정만 추출
3. **회사정보** — `mcp__dart__get_company_info`(corp_code)
4. **공시검색** — `mcp__dart__search_disclosures`(corp_code, bgn_de, end_de)

**DART 주요 계정명(JSON `account_nm`)**: 매출액 · 매출원가 · 영업이익 · 당기순이익 · 법인세차감전순이익 · 자산총계 · 부채총계 · 자본총계 · 영업활동현금흐름

**주요 corp_code**: 삼성전자 `00126380` · SK하이닉스 `00164779` · LG전자 `00401731` · **LG이노텍 `00105961`** · 현대차 `00164742` · 네이버 `00266961` · 카카오 `00258801` · 삼성SDI `00126371` · LG화학 `00356361` · 셀트리온 `00421045` · 포스코홀딩스 `00126186`

> ⚠️ **실증 함정(2026-06)**: Yahoo의 `Revenue(TTM)`는 회계연도 매출과 다를 수 있다 — LG이노텍 FY2025: Yahoo TTM **₩22.45조** vs DART 공식 연간 **₩21.90조**(편차 2.5%, >1% → 표시 대상). **회계연도 절대값은 DART 공시를 정본**으로 채택하고, Yahoo는 주가·시총 등 시장데이터에만 사용한다.

---

## 执行规范

### 第一步：获取数据

对每个财务指标（收入、净利润、毛利率、经营现金流、资产负债率等），分别从**来源1**和**来源2**取数。

### 第二步：误差计算与标记

```
误差率 = |来源1数值 - 来源2数值| / 来源1数值 × 100%
```

| 误差 | 处理方式 |
|------|---------|
| ≤ 1% | ✅ 一致，取来源1数值，标注两个来源 |
| 1% ~ 5% | ⚠️ 标记"数据存在差异"，注明两个数值，说明可能原因（汇率/会计口径） |
| > 5% | ❌ 标记"数据存在重大差异"，必须查原始财报核实，不得直接使用 |

### 第三步：数据呈现格式

每个关键数据必须按以下格式标注：

```
收入：1,239亿元 ✅
  - macrotrends: 1,241亿元
  - stockanalysis: 1,237亿元
  - 误差: 0.3%
```

差异示例：
```
净利润：245亿元 ⚠️ 数据存在差异
  - macrotrends: 245亿元（GAAP）
  - stockanalysis: 278亿元（Non-GAAP）
  - 误差: 13.5% — 原因：会计口径不同（GAAP vs Non-GAAP）
```

---

## 常见差异原因（不一定是数据错误）

| 原因 | 说明 |
|------|------|
| GAAP vs Non-GAAP | 最常见，尤其是利润类数据 |
| 汇率换算 | 港币/人民币/美元换算时间点不同 |
| 财年定义 | 自然年 vs 财年（如苹果财年10月结束） |
| 合并口径 | 是否含少数股东权益 |
| 数据更新滞后 | 某平台尚未更新最新一期财报 |

---

## 特别规则

1. **未上市公司**（米哈游、莉莉丝等）：只有一手数据来源时，数据前标记 `[估计]`，不执行交叉验证
2. **季度数据 vs 年度数据**：优先使用年度数据做交叉验证，季度数据部分来源可能有滞后
3. **原始财报优先**：若两个来源均与原始财报（10-K/年报PDF）不符，以原始财报为准，标记来源错误

---

## 快速索引

| 场景 | 主要来源 | 备用来源 |
|------|---------|---------|
| PDD / 拼多多 | macrotrends.net/stocks/charts/PDD | stockanalysis.com/stocks/pdd |
| 腾讯 | macrotrends.net/stocks/charts/TCEHY | aastocks（0700.HK） |
| 网易 | macrotrends.net/stocks/charts/NTES | aastocks（9999.HK） |
| 三七互娱 | eastmoney.com（002555） | cninfo.com.cn |
| 吉比特 | eastmoney.com（603444） | cninfo.com.cn |
| Nintendo | macrotrends.net/stocks/charts/NTDOY | stockanalysis.com/stocks/ntdoy |
| Capcom | macrotrends（CCOEY） | stockanalysis（CCOEY） |
| 삼성전자 | DART corp_code 00126380 | Yahoo 005930.KS |
| LG이노텍 | DART corp_code 00105961 | Yahoo 011070.KS |
| SK하이닉스 | DART corp_code 00164779 | Yahoo 000660.KS |
