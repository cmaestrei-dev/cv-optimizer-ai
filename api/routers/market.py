"""Mi mercado: qué piden las vacantes analizadas y cómo le va a la persona por portal."""

from fastapi import APIRouter

from api.auth import CurrentAccount
from api.schemas import KeywordOut, MarketOut, PlatformStatsOut, ScoreBucketOut
from core.profile import service
from core.tracking import service as tracking
from core.tracking.insights import build_insights

router = APIRouter(tags=["mercado"])


@router.get("/market", response_model=MarketOut)
def market(account: CurrentAccount, platform: str | None = None) -> MarketOut:
    insights = build_insights(tracking.list_applications(account.username, with_files=False), service.snapshot(account.username),
                              platform=platform)
    return MarketOut(
        applications=insights.applications, analyzed=insights.analyzed, sent=insights.sent,
        enough_data=insights.enough_data,
        platforms=[PlatformStatsOut(platform=p.platform, saved=p.saved, sent=p.sent, progressed=p.progressed,
                                    rejected=p.rejected, progress_rate=p.progress_rate, avg_score=p.avg_score)
                   for p in insights.platforms],
        keywords=[KeywordOut(keyword=k.keyword, vacancies=k.vacancies, share=k.share, owned=k.owned)
                  for k in insights.keywords],
        score_buckets=[ScoreBucketOut(range=r, sent=sent, progressed=progressed)
                       for r, sent, progressed in insights.score_buckets],
    )
