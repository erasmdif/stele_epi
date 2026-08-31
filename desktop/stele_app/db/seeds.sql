-- ============================================================================
-- Stele DBMS — seed dei vocabolari controllati (indipendenti dal backend)
-- Gli UUID sono assegnati a runtime da project.py dove servono; qui usiamo
-- valori deterministici solo per i termini citati dagli esempi.
-- ============================================================================

-- certainty_level
INSERT INTO certainty_level (code,label,rank) VALUES
 ('certain','Certain',10),('probable','Probable',20),('possible','Possible',30),
 ('uncertain','Uncertain',40),('unknown','Unknown',50);

-- reliability_level
INSERT INTO reliability_level (code,label,rank) VALUES
 ('high','High',10),('medium','Medium',20),('low','Low',30),('unknown','Unknown',40);

-- relation_type (generali)
INSERT INTO relation_type (code,label,inverse_label,domain,is_symmetric,is_hierarchical) VALUES
 ('IS_A','is a','includes','generic',0,1),
 ('PART_OF','part of','contains','generic',0,1),
 ('EQUIVALENT_TO','equivalent to','equivalent to','generic',1,0),
 ('ASSOCIATED_WITH','associated with','associated with','generic',1,0),
 ('DERIVED_FROM','derived from','source of','generic',0,0),
 ('RELATED_TO','related to','related to','generic',1,0),
 ('OVERLAPS','overlaps','overlaps','chronology_term',1,0),
 ('PRECEDES','precedes','follows','chronology_term',0,0),
 ('FOLLOWS','follows','precedes','chronology_term',0,0),
 ('SAME_SCRIBE','same scribe','same scribe','object',1,0),
 ('SAME_WORKSHOP','same workshop','same workshop','object',1,0),
 ('SAME_SCHOOL','same school','same school','object',1,0),
 ('POSSIBLE_SAME_PRODUCTION','possible same production','possible same production','object',1,0),
 ('TEXTUAL_COMPANION_OF','textual companion of','textual companion of','object',1,0),
 ('OTHER_SCIENTIFIC_ASSOCIATION','scientific association','scientific association','object',1,0);
