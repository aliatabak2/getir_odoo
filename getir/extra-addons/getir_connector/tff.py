from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen import canvas
# Courier New fontunu register et
pdfmetrics.registerFont(TTFont('Courier', 'C:/Windows/Fonts/cour.ttf'))


c = canvas.Canvas("test.pdf")
c.setFont("Courier", 12)  # Az önce register edilen font
c.drawString(100, 750, "Hello Odoo PDF!")
c.save()
