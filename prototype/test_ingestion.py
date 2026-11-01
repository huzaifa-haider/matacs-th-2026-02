import base64
import io
import unittest
import zipfile
from unittest.mock import patch
import app
import ingestion

class IngestionTests(unittest.TestCase):
    def test_text_and_evidence(self):
        sources=ingestion.read_document('a.txt',b'price: 240000\nweeks: 12\nlicence: true')
        result=ingestion.local_extract(sources)
        self.assertEqual(result['facts']['price'],240000)
        self.assertIsNone(result['facts']['projects'])
        self.assertEqual(result['evidence']['weeks'][0]['quote'],'weeks: 12')
    def test_conflicting_values(self):
        r=ingestion.local_extract({'p':'price: 240000\nprice: 250000'})
        self.assertIsNone(r['facts']['price'])
    def test_docx(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>price: 240000</w:t></w:r></w:p></w:body></w:document>')
        self.assertIn('price: 240000',ingestion.read_document('x.docx',b.getvalue()).values())
    def test_pdf(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject,NameObject,DecodedStreamObject
        w=PdfWriter();page=w.add_blank_page(width=300,height=300)
        font=DictionaryObject({NameObject('/Type'):NameObject('/Font'),NameObject('/Subtype'):NameObject('/Type1'),NameObject('/BaseFont'):NameObject('/Helvetica')})
        page[NameObject('/Resources')]=DictionaryObject({NameObject('/Font'):DictionaryObject({NameObject('/F1'):w._add_object(font)})})
        stream=DecodedStreamObject();stream.set_data(b'BT /F1 12 Tf 20 200 Td (price: 240000) Tj ET')
        page[NameObject('/Contents')]=w._add_object(stream)
        b=io.BytesIO();w.write(b)
        self.assertIn('price: 240000',ingestion.read_document('x.pdf',b.getvalue())['page:1'])
    def test_no_text_pdf(self):
        from pypdf import PdfWriter
        w=PdfWriter();w.add_blank_page(width=300,height=300);b=io.BytesIO();w.write(b)
        with self.assertRaisesRegex(ValueError,'OCR'):ingestion.read_document('x.pdf',b.getvalue())
    def test_upload_is_unapproved(self):
        p={'config':app.DEFAULT,'mode':'local','documents':[{'name':'x.txt','base64':base64.b64encode(b'price: 240000').decode()}]}
        r=ingestion.ingest(p)
        self.assertFalse(r['proposals'][0]['approved'])
        self.assertFalse(r['demo'])
    def test_ai_missing_credentials(self):
        with patch.dict('os.environ',{},clear=True):
            with self.assertRaisesRegex(ValueError,'OPENAI_API_KEY'):ingestion.ai_extract({},app.DEFAULT)
    def test_invalid_format(self):
        with self.assertRaises(ValueError):ingestion.read_document('x.exe',b'not a document')

if __name__=='__main__':unittest.main()
