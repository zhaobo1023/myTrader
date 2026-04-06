# -*- coding: utf-8 -*-
"""research: five-section full schema
  -- New tables --
  tech_snapshots       (daily)   : tech score + indicators
  fund_flow_snapshots  (daily)   : main force + north-bound flow
  valuation_daily      (daily)   : PE/PB with 1/3/5yr quantiles
  fundamental_detail   (quarterly): financial statement metrics per report period
  capital_cycle_snapshots (monthly/event): capex cycle phase + shareholder behavior
  announcements        (daily scan / event): key public disclosures
  report_metadata      (on generate): index of generated analysis reports

  -- ALTER existing tables --
  fundamental_snapshots  : + data_period, ocf_to_profit, debt_ratio
  composite_scores       : + UNIQUE KEY
  sentiment_scores       : + UNIQUE KEY

Update frequency matrix:
  Table                    | Frequency        | Trigger
  -------------------------|------------------|------------------------------
  tech_snapshots           | daily            | after market close
  fund_flow_snapshots      | daily            | after market close
  valuation_daily          | daily            | price feed
  sentiment_scores         | weekly           | scheduler
  fundamental_snapshots    | weekly (score)   | scheduler
  fundamental_detail       | quarterly        | after each earnings report
  capital_cycle_snapshots  | monthly+event    | scheduler + announcement NLP
  announcements            | daily+event      | cninfo crawl + NLP
  composite_scores         | weekly           | after sub-scores updated
  report_metadata          | on generate      | report pipeline
  sentiment_events         | event            | manual / NLP pipeline
  watchlist                | on change        | user action

Revision ID: 68fd8567e039
Revises: cc8095756cc6
Create Date: 2026-04-06
"""
from alembic import op
import sqlalchemy as sa

revision = '68fd8567e039'
down_revision = 'cc8095756cc6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. research_tech_snapshots
    #    UPDATE FREQ: daily (after market close)
    #    SOURCE: strategist/tech_scan/single_scanner.py ReportEngine
    # ------------------------------------------------------------------
    op.create_table(
        'research_tech_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False,
                  comment='6-digit stock code'),
        sa.Column('snap_date', sa.Date(), nullable=False,
                  comment='trade date of this snapshot'),

        # composite score (0-10 from ReportEngine)
        sa.Column('tech_score', sa.Numeric(4, 2), nullable=True,
                  comment='composite tech score 0.0-10.0'),
        sa.Column('trend_badge', sa.String(10), nullable=True,
                  comment='trend label: UPTREND/DOWNTREND/SIDEWAYS/REVERSAL'),
        sa.Column('action_advice', sa.String(20), nullable=True,
                  comment='action label: BUY/HOLD/REDUCE/SELL/WATCH'),

        # price & MAs
        sa.Column('close', sa.Numeric(10, 3), nullable=True),
        sa.Column('ma5', sa.Numeric(10, 3), nullable=True),
        sa.Column('ma20', sa.Numeric(10, 3), nullable=True),
        sa.Column('ma60', sa.Numeric(10, 3), nullable=True),
        sa.Column('ma250', sa.Numeric(10, 3), nullable=True),

        # MACD
        sa.Column('macd_dif', sa.Numeric(10, 4), nullable=True),
        sa.Column('macd_dea', sa.Numeric(10, 4), nullable=True),
        sa.Column('macd_hist', sa.Numeric(10, 4), nullable=True,
                  comment='MACD bar (2*histogram)'),

        # RSI
        sa.Column('rsi14', sa.Numeric(6, 2), nullable=True),

        # KDJ (9,3,3)
        sa.Column('kdj_k', sa.Numeric(6, 2), nullable=True),
        sa.Column('kdj_d', sa.Numeric(6, 2), nullable=True),
        sa.Column('kdj_j', sa.Numeric(6, 2), nullable=True),

        # BOLL (20,2)
        sa.Column('boll_upper', sa.Numeric(10, 3), nullable=True),
        sa.Column('boll_mid', sa.Numeric(10, 3), nullable=True),
        sa.Column('boll_lower', sa.Numeric(10, 3), nullable=True),

        # volume
        sa.Column('vol_ratio_5d', sa.Numeric(6, 2), nullable=True,
                  comment='volume / 5-day avg volume'),

        # signals & alerts (JSON arrays)
        sa.Column('signals_json', sa.JSON(), nullable=True,
                  comment='list of all detected signals [{type, level, desc}]'),
        sa.Column('alerts_json', sa.JSON(), nullable=True,
                  comment='list of triggered alert signals only'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'snap_date', name='uk_tech_code_date'),
    )
    op.create_index('idx_tech_code_date', 'research_tech_snapshots',
                    ['code', 'snap_date'])

    # ------------------------------------------------------------------
    # 2. research_fund_flow_snapshots
    #    UPDATE FREQ: daily (after market close, from AKShare eastmoney)
    #    SOURCE: ak.stock_individual_fund_flow / ak.stock_main_fund_flow
    # ------------------------------------------------------------------
    op.create_table(
        'research_fund_flow_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('snap_date', sa.Date(), nullable=False),

        # main force flow (万元)
        sa.Column('main_net', sa.Numeric(14, 2), nullable=True,
                  comment='main force net inflow (10k yuan)'),
        sa.Column('main_net_pct', sa.Numeric(6, 4), nullable=True,
                  comment='main_net / total turnover'),
        sa.Column('super_large_net', sa.Numeric(14, 2), nullable=True,
                  comment='super-large order net inflow'),
        sa.Column('large_net', sa.Numeric(14, 2), nullable=True,
                  comment='large order net inflow'),
        sa.Column('mid_net', sa.Numeric(14, 2), nullable=True,
                  comment='mid order net inflow'),
        sa.Column('retail_net', sa.Numeric(14, 2), nullable=True,
                  comment='retail (small) order net inflow'),

        # 5-day cumulative
        sa.Column('main_net_5d', sa.Numeric(14, 2), nullable=True),
        sa.Column('main_net_pct_5d', sa.Numeric(6, 4), nullable=True),

        # north-bound / south-bound (applicable to A-share stocks in Stock Connect)
        sa.Column('north_net', sa.Numeric(14, 2), nullable=True,
                  comment='Shanghai/Shenzhen-HK connect northbound net (10k yuan)'),

        # dragon-tiger list (龙虎榜)
        sa.Column('on_dragon_tiger', sa.Boolean(),
                  server_default='0', nullable=False),
        sa.Column('dragon_tiger_inst_buy', sa.Numeric(14, 2), nullable=True,
                  comment='institutional buy amount on dragon-tiger list'),

        sa.Column('label', sa.String(10), nullable=True,
                  comment='summary label: inflow/outflow/neutral'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'snap_date', name='uk_fundflow_code_date'),
    )
    op.create_index('idx_fundflow_code_date', 'research_fund_flow_snapshots',
                    ['code', 'snap_date'])

    # ------------------------------------------------------------------
    # 3. research_valuation_daily
    #    UPDATE FREQ: daily (fast - price-derived only)
    #    PURPOSE: real-time PE/PB quantile, decoupled from quarterly financials
    #    SOURCE: trade_stock_daily + financial_indicators
    # ------------------------------------------------------------------
    op.create_table(
        'research_valuation_daily',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),

        # current valuation multiples
        sa.Column('pe_ttm', sa.Numeric(8, 2), nullable=True),
        sa.Column('pe_lyr', sa.Numeric(8, 2), nullable=True,
                  comment='last year reported PE'),
        sa.Column('pb', sa.Numeric(6, 2), nullable=True),
        sa.Column('ps_ttm', sa.Numeric(8, 2), nullable=True),
        sa.Column('dividend_yield', sa.Numeric(6, 4), nullable=True,
                  comment='trailing 12m dividend / price'),
        sa.Column('total_mv', sa.Numeric(14, 2), nullable=True,
                  comment='total market cap (100 million yuan)'),
        sa.Column('float_mv', sa.Numeric(14, 2), nullable=True,
                  comment='float market cap (100 million yuan)'),

        # quantile positions (fraction of history <= current value)
        sa.Column('pe_q1yr', sa.Numeric(5, 3), nullable=True,
                  comment='PE percentile vs 1yr history'),
        sa.Column('pe_q3yr', sa.Numeric(5, 3), nullable=True,
                  comment='PE percentile vs 3yr history'),
        sa.Column('pe_q5yr', sa.Numeric(5, 3), nullable=True,
                  comment='PE percentile vs 5yr history'),
        sa.Column('pb_q3yr', sa.Numeric(5, 3), nullable=True),
        sa.Column('pb_q5yr', sa.Numeric(5, 3), nullable=True),

        # valuation label (cheap/fair/expensive) based on 5yr quantile
        sa.Column('val_label', sa.String(10), nullable=True,
                  comment='cheap/fair/moderate/expensive/bubble'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'trade_date', name='uk_valdaily_code_date'),
    )
    op.create_index('idx_valdaily_code_date', 'research_valuation_daily',
                    ['code', 'trade_date'])

    # ------------------------------------------------------------------
    # 4. research_fundamental_detail
    #    UPDATE FREQ: quarterly (after each earnings report)
    #    PURPOSE: store actual financial statement data per reporting period
    #    NOTE: fundamental_snapshots stores scoring, this stores raw financials
    # ------------------------------------------------------------------
    op.create_table(
        'research_fundamental_detail',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('data_period', sa.String(10), nullable=False,
                  comment='reporting period: 2024Q1 / 2024H1 / 2024Q3 / 2024FY'),
        sa.Column('report_date', sa.Date(), nullable=True,
                  comment='actual public announcement date'),

        # income statement
        sa.Column('revenue', sa.Numeric(16, 2), nullable=True,
                  comment='total revenue (100 million yuan)'),
        sa.Column('revenue_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('gross_margin', sa.Numeric(6, 4), nullable=True),
        sa.Column('net_profit', sa.Numeric(16, 2), nullable=True,
                  comment='net profit attributable to parent (100 million yuan)'),
        sa.Column('net_profit_yoy', sa.Numeric(6, 4), nullable=True),
        sa.Column('net_profit_margin', sa.Numeric(6, 4), nullable=True),
        sa.Column('eps', sa.Numeric(8, 4), nullable=True,
                  comment='earnings per share'),

        # balance sheet
        sa.Column('total_assets', sa.Numeric(16, 2), nullable=True,
                  comment='(100 million yuan)'),
        sa.Column('total_liab', sa.Numeric(16, 2), nullable=True),
        sa.Column('debt_ratio', sa.Numeric(6, 4), nullable=True,
                  comment='total_liab / total_assets'),
        sa.Column('cash', sa.Numeric(16, 2), nullable=True,
                  comment='cash and cash equivalents'),
        sa.Column('roe', sa.Numeric(6, 4), nullable=True,
                  comment='return on equity (annualised for interim)'),
        sa.Column('roa', sa.Numeric(6, 4), nullable=True),

        # cash flow
        sa.Column('ocf', sa.Numeric(16, 2), nullable=True,
                  comment='operating cash flow'),
        sa.Column('ocf_to_profit', sa.Numeric(6, 4), nullable=True,
                  comment='OCF / net profit: cash quality ratio'),
        sa.Column('capex', sa.Numeric(16, 2), nullable=True),
        sa.Column('fcf', sa.Numeric(16, 2), nullable=True,
                  comment='free cash flow = OCF - capex'),

        # derived
        sa.Column('fcf_yield', sa.Numeric(6, 4), nullable=True,
                  comment='FCF / market cap at report_date'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP'),
                  nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'data_period', name='uk_funddetail_code_period'),
    )
    op.create_index('idx_funddetail_code_period', 'research_fundamental_detail',
                    ['code', 'data_period'])
    op.create_index('idx_funddetail_report_date', 'research_fundamental_detail',
                    ['report_date'])

    # ------------------------------------------------------------------
    # 5. research_capital_cycle_snapshots
    #    UPDATE FREQ: monthly scheduler + event-triggered (announcement NLP)
    #    PURPOSE: capital cycle phase + shareholder behavior signals
    #    Phases: 1=expansion_early, 2=expansion_mid, 3=expansion_late,
    #            4=contraction, 5=clearance
    # ------------------------------------------------------------------
    op.create_table(
        'research_capital_cycle_snapshots',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('snap_date', sa.Date(), nullable=False),

        sa.Column('phase', sa.SmallInteger(), nullable=True,
                  comment='capital cycle phase 1-5'),
        sa.Column('phase_label', sa.String(20), nullable=True,
                  comment='e.g. expansion_early / contraction'),

        # capex signals
        sa.Column('capex_yoy', sa.Numeric(6, 4), nullable=True,
                  comment='capex growth yoy, last annual report'),
        sa.Column('capex_to_revenue', sa.Numeric(6, 4), nullable=True),
        sa.Column('supply_signal', sa.String(10), nullable=True,
                  comment='expanding / stable / shrinking'),

        # demand signals
        sa.Column('demand_signal', sa.String(10), nullable=True,
                  comment='growing / stable / declining'),
        sa.Column('industry_capacity_utilization', sa.Numeric(6, 4), nullable=True),

        # shareholder behavior (from announcement NLP)
        sa.Column('controlling_shareholder_net', sa.Numeric(14, 2), nullable=True,
                  comment='net shares bought/sold by controlling shareholder (positive=buy)'),
        sa.Column('founder_reducing', sa.Boolean(),
                  server_default='0', nullable=False),
        sa.Column('management_buyback', sa.Boolean(),
                  server_default='0', nullable=False,
                  comment='company buyback programme active'),

        # analyst behavior
        sa.Column('analyst_rating_avg', sa.Numeric(4, 2), nullable=True,
                  comment='avg analyst rating: 1=strong_sell .. 5=strong_buy'),
        sa.Column('analyst_count', sa.SmallInteger(), nullable=True),
        sa.Column('analyst_rating_change', sa.SmallInteger(), nullable=True,
                  comment='-1=downgrade, 0=maintain, 1=upgrade (last 30d)'),

        sa.Column('phase_note', sa.Text(), nullable=True,
                  comment='LLM or analyst narrative for current phase'),
        sa.Column('trigger', sa.String(20), nullable=True,
                  comment='what caused this update: scheduler/announcement/manual'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'snap_date', name='uk_capcy_code_date'),
    )
    op.create_index('idx_capcy_code_date', 'research_capital_cycle_snapshots',
                    ['code', 'snap_date'])

    # ------------------------------------------------------------------
    # 6. research_announcements
    #    UPDATE FREQ: daily scan (cninfo crawl) + event-driven NLP processing
    #    PURPOSE: track key disclosures; source for capital_cycle + sentiment updates
    # ------------------------------------------------------------------
    op.create_table(
        'research_announcements',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('ann_date', sa.Date(), nullable=False,
                  comment='announcement publication date'),
        sa.Column('ann_type', sa.String(20), nullable=False,
                  comment='reduce/increase/buyback/earnings_guide/dividend/major_contract/other'),
        sa.Column('title', sa.String(300), nullable=False),

        # classification (after NLP processing)
        sa.Column('direction', sa.String(10), nullable=True,
                  comment='positive/negative/neutral'),
        sa.Column('magnitude', sa.String(10), nullable=True,
                  comment='high/medium/low'),
        sa.Column('summary', sa.String(300), nullable=True,
                  comment='1-2 sentence LLM summary'),

        # metadata
        sa.Column('pdf_url', sa.String(500), nullable=True),
        sa.Column('local_pdf_path', sa.String(500), nullable=True),

        # processing status
        sa.Column('is_nlp_processed', sa.Boolean(),
                  server_default='0', nullable=False,
                  comment='whether NLP pipeline has run on this announcement'),
        sa.Column('is_ingested_rag', sa.Boolean(),
                  server_default='0', nullable=False,
                  comment='whether ingested into ChromaDB'),

        sa.Column('created_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code', 'ann_date', 'title', name='uk_ann_code_date_title'),
    )
    op.create_index('idx_ann_code_date', 'research_announcements',
                    ['code', 'ann_date'])
    op.create_index('idx_ann_unprocessed', 'research_announcements',
                    ['is_nlp_processed', 'ann_date'])

    # ------------------------------------------------------------------
    # 7. research_report_metadata
    #    UPDATE FREQ: on-generate (whenever report pipeline runs)
    #    PURPOSE: index of all generated analysis reports (one row per report)
    # ------------------------------------------------------------------
    op.create_table(
        'research_report_metadata',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(10), nullable=False),
        sa.Column('report_date', sa.Date(), nullable=False,
                  comment='report generation date'),
        sa.Column('report_type', sa.String(20), nullable=False,
                  comment='tech/fundamental/sentiment/capital_cycle/composite/full'),

        # output location
        sa.Column('file_path', sa.String(500), nullable=True),
        sa.Column('file_format', sa.String(10), nullable=True,
                  comment='md/html/pdf'),

        # score snapshot at generation time
        sa.Column('composite_score', sa.SmallInteger(), nullable=True),
        sa.Column('direction', sa.String(10), nullable=True,
                  comment='strong_bull/bull/neutral/bear/strong_bear'),
        sa.Column('score_technical', sa.SmallInteger(), nullable=True),
        sa.Column('score_fundamental', sa.SmallInteger(), nullable=True),
        sa.Column('score_sentiment', sa.SmallInteger(), nullable=True),
        sa.Column('score_fund_flow', sa.SmallInteger(), nullable=True),
        sa.Column('score_capital_cycle', sa.SmallInteger(), nullable=True),

        sa.Column('llm_model', sa.String(50), nullable=True,
                  comment='LLM model used for text generation'),
        sa.Column('generated_at', sa.DateTime(),
                  server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_report_code_date', 'research_report_metadata',
                    ['code', 'report_date'])
    op.create_index('idx_report_type_date', 'research_report_metadata',
                    ['report_type', 'report_date'])

    # ------------------------------------------------------------------
    # ALTER EXISTING TABLES
    # ------------------------------------------------------------------

    # fundamental_snapshots: add data_period + financial quality fields
    op.add_column('fundamental_snapshots',
        sa.Column('data_period', sa.String(10), nullable=True,
                  comment='source reporting period, e.g. 2024Q4 / 2024FY'))
    op.add_column('fundamental_snapshots',
        sa.Column('ocf_to_profit', sa.Numeric(6, 4), nullable=True,
                  comment='OCF / net profit'))
    op.add_column('fundamental_snapshots',
        sa.Column('debt_ratio', sa.Numeric(6, 4), nullable=True,
                  comment='total liab / total assets'))

    # composite_scores: add unique constraint (currently has no UK)
    op.create_unique_constraint(
        'uk_composite_code_date', 'composite_scores', ['code', 'score_date']
    )

    # sentiment_scores: add unique constraint
    op.create_unique_constraint(
        'uk_sentiment_score_code_date', 'sentiment_scores', ['code', 'score_date']
    )


def downgrade() -> None:
    # drop unique constraints added to existing tables
    op.drop_constraint('uk_sentiment_score_code_date', 'sentiment_scores',
                       type_='unique')
    op.drop_constraint('uk_composite_code_date', 'composite_scores',
                       type_='unique')
    op.drop_column('fundamental_snapshots', 'debt_ratio')
    op.drop_column('fundamental_snapshots', 'ocf_to_profit')
    op.drop_column('fundamental_snapshots', 'data_period')

    # drop new tables
    op.drop_index('idx_report_type_date', table_name='research_report_metadata')
    op.drop_index('idx_report_code_date', table_name='research_report_metadata')
    op.drop_table('research_report_metadata')

    op.drop_index('idx_ann_unprocessed', table_name='research_announcements')
    op.drop_index('idx_ann_code_date', table_name='research_announcements')
    op.drop_table('research_announcements')

    op.drop_index('idx_capcy_code_date', table_name='research_capital_cycle_snapshots')
    op.drop_table('research_capital_cycle_snapshots')

    op.drop_index('idx_funddetail_report_date',
                  table_name='research_fundamental_detail')
    op.drop_index('idx_funddetail_code_period',
                  table_name='research_fundamental_detail')
    op.drop_table('research_fundamental_detail')

    op.drop_index('idx_valdaily_code_date', table_name='research_valuation_daily')
    op.drop_table('research_valuation_daily')

    op.drop_index('idx_fundflow_code_date', table_name='research_fund_flow_snapshots')
    op.drop_table('research_fund_flow_snapshots')

    op.drop_index('idx_tech_code_date', table_name='research_tech_snapshots')
    op.drop_table('research_tech_snapshots')
