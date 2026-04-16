import { ImageResponse } from 'next/og';

export const runtime = 'edge';
export const alt = 'myTrader - AI 量化投研平台';
export const size = { width: 1200, height: 630 };
export const contentType = 'image/png';

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          background: 'linear-gradient(135deg, #0a0f1a 0%, #1a1f2e 100%)',
          padding: '80px',
          fontFamily: 'system-ui, "PingFang SC", "Noto Sans SC", sans-serif',
          position: 'relative',
        }}
      >
        {/* Top accent bar */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '4px', background: '#6366f1' }} />

        {/* Title */}
        <div style={{ fontSize: '72px', fontWeight: 800, color: '#ffffff', letterSpacing: '-1px' }}>
          myTrader
        </div>

        {/* Subtitle */}
        <div style={{ fontSize: '32px', color: '#a0a8c0', marginTop: '12px' }}>
          AI 量化投研平台
        </div>

        {/* Tags */}
        <div style={{ display: 'flex', gap: '12px', marginTop: '40px' }}>
          {['智能选股', 'AI 研报', '因子分析', '风险管理'].map((tag) => (
            <div
              key={tag}
              style={{
                fontSize: '22px',
                color: '#818cf8',
                padding: '8px 20px',
                borderRadius: '8px',
                background: 'rgba(99, 102, 241, 0.12)',
                border: '1px solid rgba(99, 102, 241, 0.25)',
              }}
            >
              {tag}
            </div>
          ))}
        </div>

        {/* Bottom bar */}
        <div
          style={{
            position: 'absolute',
            bottom: 0,
            left: 0,
            right: 0,
            height: '56px',
            background: 'rgba(255,255,255,0.04)',
            display: 'flex',
            alignItems: 'center',
            paddingLeft: '80px',
          }}
        >
          <div style={{ fontSize: '18px', color: '#6b7280' }}>mytrader.cc</div>
        </div>
      </div>
    ),
    { ...size },
  );
}
