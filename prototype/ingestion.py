"""Document text extraction and optional evidence-grounded AI extraction."""
import base64
import hashlib
import io
import json
import os
import re
import urllib.request
import urllib.error
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

FIELDS = ['licence','wsib','insurance','projects','price','weeks','panel','workmanship','lead','crew','safety','monitoring']
BOOLS = {'licence','wsib','lead','crew','safety','monitoring'}

def read_document(name, raw):
    if not raw or len(raw) > 10_000_000:
        raise ValueError('Document must be between 1 byte and 10 MB.')
    ext = Path(name).suffix.lower()
    if ext == '.pdf':
        if not raw.startswith(b'%PDF-'):
            raise ValueError('Invalid PDF signature.')
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError('Install PDF support: python -m pip install -r requirements.txt')
        try:
            reader = PdfReader(io.BytesIO(raw))
            if reader.is_encrypted:
                raise ValueError('Encrypted PDFs are not supported. Upload an unlocked copy.')
            if len(reader.pages) > 50:
                raise ValueError('Maximum 50 PDF pages per document.')
            sources = {f'page:{i+1}': page.extract_text() or '' for i,page in enumerate(reader.pages)}
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError('PDF could not be read.') from exc
        if any(not text.strip() for text in sources.values()):
            raise ValueError('One or more PDF pages have no readable text. Apply OCR and upload again; no pages were silently skipped.')
    elif ext == '.docx':
        try:
            with zipfile.ZipFile(io.BytesIO(raw)) as z:
                if sum(i.file_size for i in z.infolist()) > 20_000_000:
                    raise ValueError('Expanded DOCX exceeds 20 MB.')
                root = ET.fromstring(z.read('word/document.xml'))
                ns = {'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                sources = {f'paragraph:{i+1}': ''.join(t.text or '' for t in p.findall('.//w:t',ns)) for i,p in enumerate(root.findall('.//w:p',ns))}
                sources = {k:v for k,v in sources.items() if v.strip()}
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as exc:
            raise ValueError('Invalid DOCX document.') from exc
    elif ext in ('.txt','.md'):
        try:
            sources = {'text:1':raw.decode('utf-8-sig')}
        except UnicodeDecodeError as exc:
            raise ValueError('Text files must use UTF-8 encoding.') from exc
    else:
        raise ValueError('Supported formats: PDF, DOCX, TXT and Markdown.')
    if not sources or not ''.join(sources.values()).strip():
        raise ValueError('Document contains no readable text.')
    if sum(map(len,sources.values())) > 100_000:
        raise ValueError('Extracted text exceeds 100,000 characters.')
    return sources

def local_extract(sources):
    # Offline fallback deliberately accepts explicit field:value lines only.
    facts = dict.fromkeys(FIELDS)
    evidence = {}
    warnings = ['Local field parser: free-form prose needs AI extraction or manual review.']
    for sid,text in sources.items():
        if re.search(r'ignore.{0,30}instructions|rank.{0,20}first|full marks|pre-approved',text,re.I):
            warnings.append('Instruction-like content detected in '+sid+'; review it as untrusted data.')
        for k in FIELDS:
            matches = list(re.finditer(r'^\s*'+k+r'\s*:\s*(true|false|[0-9][0-9,]*(?:\.[0-9]+)?)\s*$',text,re.I|re.M))
            for m in matches:
                value = m.group(1).lower()
                if k in BOOLS:
                    if value not in ('true','false'): continue
                    value = value == 'true'
                else:
                    if value in ('true','false'): continue
                    value = float(value.replace(',',''))
                if k in evidence and facts[k] != value:
                    facts[k] = None
                    warnings.append('Conflicting '+k+' values; reviewer must resolve.')
                elif k not in evidence:
                    facts[k] = value
                evidence.setdefault(k,[]).append({'source_id':sid,'quote':m.group(0)})
    return {'facts':facts,'evidence':evidence,'warnings':warnings}

def ai_extract(sources, config):
    key, model = os.environ.get('OPENAI_API_KEY'), os.environ.get('OPENAI_MODEL')
    if not key or not model:
        raise ValueError('Set OPENAI_API_KEY and OPENAI_MODEL on the server to enable AI extraction. Local text extraction still works without them.')
    prompt = Path(__file__).with_name('extraction_prompt.txt').read_text(encoding='utf-8')
    properties = {k:{'type':['boolean','null'] if k in BOOLS else ['number','null']} for k in FIELDS}
    quote = {'type':'object','properties':{'source_id':{'type':'string'},'quote':{'type':'string'}},'required':['source_id','quote'],'additionalProperties':False}
    schema = {'type':'object','properties':{'facts':{'type':'object','properties':properties,'required':FIELDS,'additionalProperties':False},'evidence':{'type':'object','properties':{k:{'type':'array','items':quote} for k in FIELDS},'required':FIELDS,'additionalProperties':False},'warnings':{'type':'array','items':{'type':'string'}}},'required':['facts','evidence','warnings'],'additionalProperties':False}
    body = {'model':model,'instructions':prompt,'input':json.dumps({'config':config,'sources':sources}), 'store':False,'max_output_tokens':8000,'text':{'format':{'type':'json_schema','name':'proposal_facts','strict':True,'schema':schema}}}
    request = urllib.request.Request('https://api.openai.com/v1/responses',data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=90) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise ValueError('AI service returned HTTP '+str(exc.code)+'. Check model access, API key and quota; no score was generated.') from exc
    except (urllib.error.URLError,TimeoutError) as exc:
        raise ValueError('AI request failed or timed out. Retry explicitly; no score was generated.') from exc
    if result.get('status') != 'completed':
        raise ValueError('AI response was incomplete; extraction was not accepted.')
    text = ''.join(c.get('text','') for item in result.get('output',[]) for c in item.get('content',[]) if c.get('type')=='output_text')
    try:
        return json.loads(text)
    except ValueError as exc:
        raise ValueError('AI did not return valid extraction JSON.') from exc

def ingest(payload):
    from app import validate_config, validate_proposal
    config = payload['config']
    validate_config(config)
    documents = payload['documents']
    if not isinstance(documents,list) or not 1 <= len(documents) <= 5:
        raise ValueError('Upload 1–5 documents; one proposal per document.')
    mode = payload.get('mode','local')
    if mode not in ('local','ai'):
        raise ValueError('Unknown extraction mode.')
    proposals, hashes = [],set()
    for index,doc in enumerate(documents):
        try:
            raw = base64.b64decode(doc['base64'],validate=True)
        except (ValueError,TypeError) as exc:
            raise ValueError('Invalid document encoding.') from exc
        digest = hashlib.sha256(raw).hexdigest()
        if digest in hashes:
            raise ValueError('Duplicate document in upload.')
        hashes.add(digest)
        sources = read_document(doc['name'],raw)
        extracted = ai_extract(sources,config) if mode=='ai' else local_extract(sources)
        p = {'id':doc.get('id') or chr(65+index),'facts':extracted['facts'],'evidence':extracted['evidence'],'warnings':extracted['warnings'],'sources':sources,'approved':False,'failed_documentation':False,'review_note':'','document':{'name':Path(doc['name']).name,'sha256':digest},'extraction':{'method':mode,'model':os.environ.get('OPENAI_MODEL') if mode=='ai' else None,'config_sha256':hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()}}
        validate_proposal(p)
        for k,v in p['facts'].items():
            if v is not None and not p['evidence'].get(k):
                raise ValueError('Extraction omitted evidence for '+k)
        proposals.append(p)
    return {'config':config,'proposals':proposals,'demo':False,'actor':'','reason':''}
