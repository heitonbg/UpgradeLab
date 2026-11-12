"""Explain missing categories without calling rejected candidates nonexistent."""
from app.services.component_quality import quality_check

def missing_diagnostic(category,candidates,eligible,allocation,compatible,board=None):
    accepted=[row for row in eligible if compatible(row)]
    rejected=[]
    eligible_ids={row.id for row in eligible}
    for row in candidates:
        if row.id in eligible_ids:continue
        quality,reason=quality_check(row) if category in ('psu','storage','cooler') else (True,None)
        rejected.append({'offer_id':row.id,'reason':'quality_rejected' if not quality else 'filtered',
                         'detail':reason or 'Не прошло ограничения подбора, бюджета или совместимости'})
    if not candidates:reason='no_offers'
    elif not eligible:reason='quality_rejected' if rejected and all(r['reason']=='quality_rejected' for r in rejected) else 'candidates_rejected'
    elif not accepted:reason='compatibility'
    elif min(row.price_rub for row in accepted)>allocation:reason='outside_budget'
    else:reason='compatibility'
    technical=[]
    if board is not None and category=='storage':
        from app.services.technical_evidence import storage_status
        technical=[{'offer_id':row.id,**storage_status(board,row)} for row in eligible]
        if not accepted and technical:
            reason='insufficient_characteristics' if any(r['status']=='unknown' for r in technical) else 'incompatible'
    if category=='psu' and candidates:
        from app.services.technical_evidence import psu_status
        technical=[{'offer_id':row.id,**psu_status(row)} for row in candidates]
        if not eligible and all(r['status']=='unknown' for r in technical):reason='model_unconfirmed'
    return {'technical_rejections':technical,'candidate_count':len(candidates),'eligible_candidate_count':len(eligible),
        'compatible_candidate_count':len(accepted),'rejected_candidates':rejected,
        'observed_min_price':min((row.price_rub for row in eligible),default=None),
        'blocking_reason':reason,'budget_is_estimate':True}
