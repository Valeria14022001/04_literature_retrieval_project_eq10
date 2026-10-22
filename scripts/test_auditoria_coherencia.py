"""Pruebas de alertas, recuperación de contexto y rechazo de ambigüedad."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('audit',Path(__file__).with_name('04b_auditar_coherencia.py'))
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class AuditTests(unittest.TestCase):
    def codes(self,text):
        return {a['codigo'] for a in audit.detect(text)}

    def test_closed_passage(self):
        self.assertEqual(self.codes('Al llegar al pueblo, descubrió la casa. Después regresó.'),set())

    def test_dependent_start_is_low_priority(self):
        alerts=audit.detect('Por eso decidió aceptar. Al día siguiente partió.')
        self.assertIn('inicio_dependiente',{a['codigo'] for a in alerts})
        self.assertEqual(next(a['prioridad'] for a in alerts if a['codigo']=='inicio_dependiente'),'baja')

    def test_unfinished_connector(self):
        self.assertIn('final_conector',self.codes('Decidió esperar porque'))
        self.assertIn('final_sin_cierre',self.codes('Decidió esperar porque'))

    def test_dialogue_does_not_imply_error(self):
        alerts=audit.detect('—Volveré mañana —dijo ella.')
        self.assertEqual([(a['codigo'],a['prioridad']) for a in alerts],[('dialogo_inicial','baja')])

    def test_integrity_and_quotation(self):
        self.assertIn('caracteres_anomalos',self.codes('Comenzó así: \ufffd.'))
        self.assertIn('delimitador_desbalanceado',self.codes('«Regresaré mañana.'))
        self.assertIn('posible_separador_perdido',self.codes('Llegó.Caminó hasta la casa.'))

    def test_paragraphs_and_flattened_fallback(self):
        self.assertEqual(audit.edge_units('Uno.\n\nDos.')[:2],('Uno.','Dos.'))
        self.assertIn('ausentes',audit.edge_units('Uno. Dos.')[2])

    def test_literal_and_ambiguous(self):
        text='Este es el pasaje original.'
        self.assertEqual(audit.locate(text,'Antes. '+text+' Después.')['inicio'],7)
        self.assertNotIn('inicio',audit.locate(text,text+' '+text))

    def test_mapping_preserves_original_characters(self):
        fragment='—'+('Una palabra larga y una historia. '*8)+'perfectamente.'
        source='Antes. '+fragment.replace('—','–').replace('perfectamente','perfec-\ntamente').replace(' ','  ')+' Después.'
        match=audit.locate(fragment,source)
        self.assertTrue(match['estado'].startswith('Vista auxiliar'))
        original=source[match['inicio']:match['fin']]
        self.assertEqual(audit.canonical(original)[0],audit.canonical(fragment)[0])
        self.assertEqual(source[:match['inicio']], 'Antes. ')

    def test_internal_header_approximate_and_repeated_rejected(self):
        text=' '.join(f'palabra{i}' for i in range(150))+'.'
        point=text.index('palabra75 ')
        source='Antes. '+text[:point]+'\nCAPÍTULO IV\n'+text[point:]+' Después.'
        found=audit.locate(text,source)
        self.assertTrue(found['estado'].startswith('Aproximada'))
        self.assertIn('CAPÍTULO IV',source[found['inicio']:found['fin']])
        self.assertNotIn('inicio',audit.locate(text,source+' '+source))


if __name__=='__main__':
    unittest.main()
