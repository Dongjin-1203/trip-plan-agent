import type { TraceStay } from "@/lib/types";

export default function StayCards({ stays }: { stays: TraceStay[] }) {
  return (
    <div>
      <div className="stay-cards">
        {stays.map((s) => (
          <article key={s.gid} className="stay">
            {s.image ? (
              // 외부(마이리얼트립) 이미지라 next/image 최적화 없이 그대로 쓴다.
              <img className="stay-img" src={s.image} alt={`${s.name} 사진`} loading="lazy" referrerPolicy="no-referrer" />
            ) : (
              <div className="stay-img none" aria-hidden>사진 없음</div>
            )}
            <div className="stay-body">
              <strong>{s.name}</strong>
              {s.description && <div className="small muted">{s.description}</div>}
              <div className="small">
                {s.rating != null && <span>평점 {s.rating}{s.review_count ? ` (${s.review_count})` : ""} · </span>}
                <span className="stay-price">{s.price || "가격 정보 없음"}</span>
              </div>
              {s.price_with_tax && <div className="small muted">{s.price_with_tax}</div>}
              {s.tags && s.tags.length > 0 && (
                <div className="stay-tags">
                  {s.tags.map((t) => (
                    <span key={t} className="chip chip-ok">{t}</span>
                  ))}
                </div>
              )}
              <a
                className="btn btn-pill"
                href={s.booking_link}
                target="_blank"
                rel="noopener noreferrer"
                aria-label={`${s.name} 예약 페이지 열기 (새 탭)`}
              >
                예약 페이지 <span aria-hidden>↗</span>
              </a>
            </div>
          </article>
        ))}
      </div>
      <p className="muted small stay-note">가격과 객실 현황은 조회 시점 기준이며 바뀔 수 있어요. 예약은 마이리얼트립 페이지에서 직접 진행해 주세요.</p>
    </div>
  );
}
