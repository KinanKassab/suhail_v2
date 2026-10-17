"""Generate PDF in memory; no patient records are written into static folders."""
from flask import render_template
from weasyprint import HTML


def generate_pdf(rec):
    markup = render_template("report.html", rec=rec, results=rec["results"])
    return HTML(string=markup).write_pdf()
