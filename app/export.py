from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.utils import simpleSplit
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, KeepTogether
from xml.sax.saxutils import escape

from .schemas import WorkoutPlan


def pdf_bytes(plan: WorkoutPlan, version_number: int) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=(612, 792), leftMargin=48, rightMargin=48,
                            topMargin=48, bottomMargin=48, title="FitBuddy workout plan")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleFit", parent=styles["Title"], textColor=colors.HexColor("#144d40"), alignment=TA_CENTER, spaceAfter=12))
    styles.add(ParagraphStyle(name="DayFit", parent=styles["Heading2"], textColor=colors.HexColor("#144d40"), spaceBefore=16))
    styles.add(ParagraphStyle(name="BodyFit", parent=styles["BodyText"], leading=15, spaceAfter=6))
    story = [Paragraph(escape(plan.title), styles["TitleFit"]),
             Paragraph(f"Plan version {version_number}", styles["BodyFit"]),
             Paragraph(escape(plan.summary), styles["BodyFit"]), Spacer(1, 8)]
    for day in sorted(plan.days, key=lambda d: d.day_number):
        intro = [Paragraph(f"Day {day.day_number}: {escape(day.focus)}" + (" (Recovery)" if day.is_rest_day else ""), styles["DayFit"]),
                 Paragraph(f"<b>Warm-up:</b> {escape(day.warmup)}", styles["BodyFit"])]
        story.append(KeepTogether(intro))
        for ex in day.exercises:
            description = f"{ex.name}: {ex.sets} sets, {ex.reps_or_duration}; rest {ex.rest_seconds} seconds"
            story.append(Paragraph("• " + escape(description), styles["BodyFit"]))
        story += [Paragraph(f"<b>Cooldown:</b> {escape(day.cooldown)}", styles["BodyFit"]),
                  Paragraph(escape(day.note), styles["BodyFit"])]
    story += [Spacer(1, 10), Paragraph("General nutrition or recovery tip", styles["DayFit"]),
              Paragraph(escape(plan.nutrition_tip), styles["BodyFit"]),
              Paragraph("General wellness information. Stop an activity that causes pain; seek qualified advice when needed.", styles["BodyFit"])]
    doc.build(story)
    return buffer.getvalue()
