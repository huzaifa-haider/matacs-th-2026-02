import copy
import json
import tempfile
import unittest
from pathlib import Path
import app

class TriageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=Path(__file__).parent)
        app.DATA = Path(self.temp.name)
        self.p = json.loads(Path(__file__).with_name('demo.json').read_text())
        self.p.update(actor='Test reviewer', reason='Automated test')
    def tearDown(self):
        self.temp.cleanup()
    def test_expected_ranking(self):
        r = app.make_run(self.p)['results']
        self.assertEqual([(x['proposal'],x['score']) for x in r[:2]], [('A',87.76),('E',75.85)])
        self.assertEqual([x['status'] for x in r[2:]], ['ineligible','flagged','flagged'])
    def test_failure_precedes_unknowns(self):
        b = self.p['proposals'][1]
        self.assertEqual(app.evaluate(b,app.DEFAULT,True,True)['status'],'ineligible')
    def test_unreviewed_is_held(self):
        self.assertEqual(app.evaluate(self.p['proposals'][0],app.DEFAULT)['status'],'flagged')
    def test_real_import_requires_evidence(self):
        self.p['demo'] = False
        with self.assertRaisesRegex(ValueError,'Missing evidence'):
            app.make_run(self.p)
    def test_fabricated_quote_rejected(self):
        a=self.p['proposals'][0]
        a['sources']={'p1':'source text'}
        a['evidence']={'price':[{'source_id':'p1','quote':'invented'}]}
        with self.assertRaisesRegex(ValueError,'does not match'):
            app.make_run(self.p)
    def test_config_validation(self):
        self.p['config']['weights']['team']=20
        with self.assertRaises(ValueError): app.make_run(self.p)
    def test_invalid_numbers(self):
        for value in [0,-1,float('nan'),True]:
            self.p['proposals'][0]['facts']['price']=value
            with self.assertRaises(ValueError): app.make_run(self.p)
    def test_immutable_snapshots(self):
        first=app.make_run(self.p)
        self.p['config']['budget']=230000
        second=app.make_run(self.p)
        with app.connect() as db:
            rows=db.execute('SELECT payload FROM runs ORDER BY id').fetchall()
        self.assertNotEqual(first['id'],second['id'])
        self.assertEqual(json.loads(rows[0][0])['config']['budget'],260000)
    def test_exact_ties(self):
        a=copy.deepcopy(self.p['proposals'][0]);a['id']='Z'
        self.p['proposals']=[a,self.p['proposals'][0]]
        r=app.make_run(self.p)['results']
        self.assertEqual([x['proposal'] for x in r],['A','Z'])
        self.assertIn('Equal merit',r[0]['reason'])

if __name__=='__main__': unittest.main()
