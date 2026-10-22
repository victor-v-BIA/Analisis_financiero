import io
import pandas as pd
from xml.sax.saxutils import escape
from PIL import Image as PILImage
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image as RLImage, KeepTogether
from reportlab.pdfgen import canvas

class NumberedCanvas(canvas.Canvas):
    """
    Canvas personalizado para calcular el total de páginas e incluir 
    un pie de página corporativo con numeración dinámica.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_footer(num_pages)
            super().showPage()
        super().save()

    def draw_footer(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 9)
        self.setFillColor(colors.HexColor("#555555"))
        
        self.setStrokeColor(colors.HexColor("#D1D5DB"))
        self.setLineWidth(0.75)
        self.line(54, 45, letter[0] - 54, 45)
        
        footer_left = "Reporte Financiero Automatizado"
        page_text = f"Página {self._pageNumber} de {page_count}"
        
        self.drawString(54, 30, footer_left)
        self.drawRightString(letter[0] - 54, 30, page_text)
        self.restoreState()


def get_base_styles():
    styles = getSampleStyleSheet()
    PRIMARY_COLOR = colors.HexColor("#1E3A8A")
    TEXT_COLOR = colors.HexColor("#1F2937")
    
    custom_styles = {
        "Title": ParagraphStyle(
            'CorpTitle',
            parent=styles.get('Heading1', styles['Normal']),
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=PRIMARY_COLOR,
            spaceAfter=6
        ),
        "Subtitle": ParagraphStyle(
            'CorpSubtitle',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=14,
            textColor=colors.HexColor("#4B5563"),
            spaceAfter=15
        ),
        "Heading": ParagraphStyle(
            'CorpHeading',
            parent=styles['Normal'],  # Heredamos directamente de 'Normal' para evitar errores
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=16,
            textColor=PRIMARY_COLOR,
            spaceBefore=18,
            spaceAfter=6,
            keepWithNext=True # Evita títulos huérfanos al final de la página
        ),
        "Body": ParagraphStyle(
            'CorpBody',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=10,
            leading=14,
            textColor=TEXT_COLOR,
            spaceAfter=8
        ),
        "Callout": ParagraphStyle(
            'CorpCallout',
            parent=styles['Normal'],
            fontName='Helvetica-Oblique',
            fontSize=10,
            leading=14,
            textColor=colors.HexColor("#1F2937"),
            spaceBefore=4,
            spaceAfter=4
        )
    }
    return custom_styles


def create_callout_box(text, styles):
    p = Paragraph(text, styles["Callout"])
    box_table = Table([[p]], colWidths=[letter[0] - 108])
    box_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F3F4F6")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1E3A8A")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    return box_table


def plotly_fig_to_reportlab_image(fig, width_pt=500, height_pt=None):
    img_bytes = fig.to_image(format="png", width=1000, height=600, scale=2)
    img_buffer = io.BytesIO(img_bytes)
    pil_img = PILImage.open(img_buffer)
    orig_width, orig_height = pil_img.size
    
    aspect_ratio = orig_height / orig_width
    
    if height_pt is None:
        calc_width = width_pt
        calc_height = width_pt * aspect_ratio
    else:
        calc_width = width_pt
        calc_height = height_pt

    img_buffer.seek(0)
    return RLImage(img_buffer, width=calc_width, height=calc_height)


def generate_modular_pdf(
    title: str,
    subtitle: str,
    elements: list
) -> bytes:
    buffer = io.BytesIO()
    
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=65
    )
    
    styles = get_base_styles()
    
    # Estilos independientes sin heredar de ningún diccionario externo
    heading_style = ParagraphStyle(
        'CorpHeadingStrict',
        fontName='Helvetica-Bold',
        fontSize=13,
        leading=16,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=18,
        spaceAfter=6,
        keepWithNext=True
    )
    
    chart_title_style = ParagraphStyle(
        'ChartTitle',
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1E3A8A"),
        spaceBefore=8,
        spaceAfter=2,
        keepWithNext=True
    )

    note_style = ParagraphStyle(
        'NoteStyle',
        fontName='Helvetica-Oblique',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor("#4B5563"),
        spaceAfter=4
    )
    
    story = []
    
    story.append(Paragraph(title, styles["Title"]))
    story.append(Paragraph(subtitle, styles["Subtitle"]))
    story.append(Spacer(1, 10))
    
    for el in elements:
        el_type = el.get("type")
        
        if el_type == "heading":
            # Si es un título independiente sin gráfica directa
            story.append(Paragraph(el["text"], heading_style))
            
        elif el_type == "callout":
            if el.get("text") and el["text"].strip():
                story.append(create_callout_box(el["text"], styles))
                story.append(Spacer(1, 10))
                
        elif el_type == "table":
            table_block = []
            if "section_title" in el:
                table_block.append(Paragraph(el["section_title"], heading_style))
                table_block.append(Spacer(1, 4))
            if "title" in el:
                table_block.append(Paragraph(el["title"], chart_title_style))
                table_block.append(Spacer(1, 4))
            
            df = el["df"]
            if df is not None and not df.empty:
                cols = list(df.columns)
                num_cols = len(cols)
                total_width = 504  # Ancho total imprimible

                # Estilos de párrafo para celdas
                th_style = ParagraphStyle(
                    'TableHeaderStyle',
                    fontName='Helvetica-Bold',
                    fontSize=8,
                    leading=10,
                    textColor=colors.white,
                    alignment=1
                )
                
                td_style_left = ParagraphStyle(
                    'TableCellStyleLeft',
                    fontName='Helvetica',
                    fontSize=7,
                    leading=9,
                    textColor=colors.HexColor("#1F2937"),
                    alignment=0
                )
                
                td_style_center = ParagraphStyle(
                    'TableCellStyleCenter',
                    fontName='Helvetica',
                    fontSize=7,
                    leading=9,
                    textColor=colors.HexColor("#1F2937"),
                    alignment=1
                )

                # Estilo específico para tablas de resumen de 1 sola columna (Método de cobro)
                td_style_single = ParagraphStyle(
                    'TableCellSingleStyle',
                    fontName='Helvetica',
                    fontSize=8,
                    leading=11,
                    textColor=colors.HexColor("#1F2937"),
                    alignment=0
                )

                # Definir anchos de columna según el tipo de tabla
                if num_cols == 1:
                    col_widths = [total_width]
                elif "Razón Social" in cols:
                    widths_dict = {
                        "RFC": 85,
                        "Facturación Total": 95,
                        "Razón Social": 264,
                        "%": 60
                    }
                    col_widths = [widths_dict.get(c, total_width / num_cols) for c in cols]
                else:
                    col_widths = [total_width / max(num_cols, 1)] * num_cols

                # Construir encabezados y filas
                header_row = [Paragraph(f"<b>{c}</b>", th_style) for c in cols] if num_cols > 1 else []
                
                body_rows = []
                for _, row in df.iterrows():
                    row_cells = []
                    for c in cols:
                        val = str(row[c]) if pd.notnull(row[c]) else ""
                        if num_cols == 1:
                            row_cells.append(Paragraph(val, td_style_single))
                        else:
                            align_style = td_style_left if c in ["Razón Social", "Cliente", "Concepto"] else td_style_center
                            row_cells.append(Paragraph(val, align_style))
                    body_rows.append(row_cells)

                table_data = ([header_row] if header_row else []) + body_rows

                t = Table(table_data, colWidths=col_widths)
                
                if num_cols == 1:
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor("#F9FAFB")),
                        ('TOPPADDING', (0, 0), (-1, -1), 5),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                        ('LEFTPADDING', (0, 0), (-1, -1), 10),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
                        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                    ]))
                else:
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#1E3A8A")),
                        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                        ('TOPPADDING', (0, 0), (-1, -1), 4),
                        ('LEFTPADDING', (0, 0), (-1, -1), 4),
                        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
                        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9FAFB")]),
                        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
                    ]))
                
                table_block.append(t)
                note_text = el.get("note", "").strip()
                if note_text:
                    table_block.append(Spacer(1, 10))
                    table_block.append(Paragraph(
                        f"<b>Conclusión:</b> {escape(note_text)}",
                        note_style
                    ))
                table_block.append(Spacer(1, 12))
                story.append(KeepTogether(table_block))
        elif el_type == "image":
            fig = el["fig"]
            if fig is not None:
                section_content = []
                
                # Opcional: si viene el título de la sección, lo unimos al bloque protegido de la gráfica
                if "section_title" in el:
                    section_content.append(Paragraph(el["section_title"], heading_style))
                    section_content.append(Spacer(1, 4))
                
                if "title" in el:
                    section_content.append(Paragraph(el["title"], chart_title_style))
                    section_content.append(Spacer(1, 2))
                
                # Soportar un alto personalizado (custom_height) para gráficas que requieran más espacio vertical
                custom_height = el.get("custom_height", None)
                if custom_height:
                    img = plotly_fig_to_reportlab_image(fig, width_pt=350, height_pt=custom_height)
                else:
                    img = plotly_fig_to_reportlab_image(fig, width_pt=450)
                    
                section_content.append(img)
                
                note_text = el.get("note", "").strip()
                if note_text:
                    section_content.append(Spacer(1, 4))
                    section_content.append(Paragraph(
                        f"<b>Conclusión:</b> {escape(note_text)}",
                        note_style
                    ))
                
                section_content.append(Spacer(1, 10))
                
                # ¡Esto obliga a que el título de sección, de gráfica, imagen y nota viajen juntos o salten de hoja!
                story.append(KeepTogether(section_content))

        elif el_type == "metrics":
            metrics_block = []
            if "title" in el:
                metrics_block.append(Paragraph(el["title"], chart_title_style))
                metrics_block.append(Spacer(1, 4))
            
            metrics_list = el.get("data", [])
            if metrics_list:
                num_cols = len(metrics_list)
                col_width = 504 / max(num_cols, 1)
                
                labels_row = [Paragraph(f"<b>{m[0]}</b>", ParagraphStyle('MLabel', fontName='Helvetica-Bold', fontSize=8, textColor=colors.HexColor("#4B5563"), alignment=1)) for m in metrics_list]
                values_row = [Paragraph(f"<b>{m[1]}</b>", ParagraphStyle('MValue', fontName='Helvetica-Bold', fontSize=14, textColor=colors.HexColor("#1E3A8A"), alignment=1)) for m in metrics_list]
                helps_row = [Paragraph(f"<font size=7 color='#6B7280'>{m[2]}</font>", ParagraphStyle('MHelp', fontName='Helvetica', fontSize=7, textColor=colors.HexColor("#6B7280"), alignment=1)) for m in metrics_list]
                
                metric_table_data = [labels_row, values_row, helps_row]
                
                mt = Table(metric_table_data, colWidths=[col_width] * num_cols)
                mt.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F9FAFB")),
                    ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
                    ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E5E7EB")),
                    ('TOPPADDING', (0,0), (-1,-1), 6),
                    ('BOTTOMPADDING', (0,0), (-1,-1), 6),
                    ('LEFTPADDING', (0,0), (-1,-1), 6),
                    ('RIGHTPADDING', (0,0), (-1,-1), 6),
                    ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                ]))
                metrics_block.append(mt)
                metrics_block.append(Spacer(1, 12))
                story.append(KeepTogether(metrics_block))
                
    doc.build(story, canvasmaker=NumberedCanvas)
    buffer.seek(0)
    return buffer.getvalue()
