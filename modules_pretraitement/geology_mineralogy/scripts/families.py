"""Mineral families shared by Earth, Mars and the Moon, and the EMIT spectral library mapped onto them.

The families are groups that orbital spectrometers also detect on Mars (CRISM, OMEGA) and on the Moon
(M3): this is what makes an Earth cell comparable with a Martian or lunar reference area.
"""

from __future__ import annotations

import re

import numpy as np

# Fixed order: it is the order of the composition vector
MINERAL_FAMILIES = [
    "oxyde_fer",        # iron oxides: hematite, goethite, ferrihydrite (Fe3+)
    "pyroxene",         # basalts: lunar maria, Martian plains
    "olivine",          # primitive basalts (Jezero, Nili Fossae)
    "feldspath",        # plagioclase: lunar highlands (weak signal in EMIT)
    "mafique_autre",    # other mafics: amphiboles, garnets, generic Fe2+
    "argile_al",        # Al clays: kaolinite, montmorillonite, beidellite
    "argile_fe_mg",     # Fe/Mg clays: nontronite, saponite, chlorite, serpentine, vermiculite, talc
    "mica",             # muscovite, illite, biotite
    "carbonate",        # calcite, dolomite, magnesite, siderite
    "sulfate",          # gypsum, jarosite, alunite, kieserite
    "silice_hydratee",  # hydrated silica: opal, chalcedony, hydrated basaltic glass
    "sel",              # salts: perchlorates, chlorides, nitrates, borates
    "autre_mineral",    # other minerals: sulfides, zeolites, epidote... (hardly comparable)
]
# Not minerals: used as masks or quality indicators, never in the score
NON_MINERAL_FAMILIES = ["vegetation", "artificiel", "revetement"]
ALL_FAMILIES = MINERAL_FAMILIES + NON_MINERAL_FAMILIES

# EMIT L2B spectral library entries, in index order (index 1 first), from the official grouping table:
# https://github.com/emit-sds/emit-sds-l2b/blob/main/data/mineral_grouping_matrix_20230503.csv
EMIT_LIBRARY = (
    'organic_green_plastic_tarp_1um', 'fe3+_hematite.fine.gr.gds76', 'fe3+_goethite.medgr.ws222',
    'fe3+_goethite+qtz.medgr.gds240', 'fe3+_goethite.fingr', 'fe3+_goethite.medcoarsegr.mpc.trjar',
    'fe3+_goethite.coarsegr', 'fe3+_goethite.thincoat', 'fe3+_goeth+jarosite', 'sulfide_pyrite',
    'fe3+_sulfate_schwertmannite', 'Mn-Coating', 'fe3+mix_AMD.assemb1', 'fe3+mix_AMD.assemb2',
    'fe3+_sulfate_kjarosite200', 'fe3+_goethite.lepidocrosite', 'fe2+_chlor+muscphy', 'fe2+_goeth+musc',
    'fe2+fe3+_chlor+goeth.propylzone', 'fe2+generic_nrw.cummingtonite', 'fe2+generic_nrw.actinolite',
    'fe2+generic_nrw.hs-actinolite', 'fe2+_pyroxene.hypersthene', 'fe2+_pyroxene.diopside',
    'fe2+generic_med.jadeite', 'fe2+_pyroxene_clino_pigeonite', 'epidote', 'fe3+bearing1',
    'fe3+_ferrihydrite', 'fe3+_hematite.med.gr.gds27', 'fe3+_hematite.thincoat',
    'fe3+_hematite.fine.gr.fe2602', 'fe3+_hematite.fine.gr.ws161', 'fe3+_smectite_nontronite',
    'fe2+generic_brd.br5a_actinolite', 'fe2+fe3+mix_with_hematite_br5b', 'fe2+generic_brd.br22c_actinolite',
    'fe2+generic_br33a_bioqtzmonz_epidote', 'fe2+generic_brd.br36a_chlorite', 'fe2+fe3+_hematite_weathering',
    'fe2+generic_basalt_br46b', 'fe3+_hematite.lg.gr.br25a', 'fe3+_hematite.med.gr.br25b',
    'fe3+_hematite.lg.gr.br25c', 'fe3+_hematite.nano.BR34b2', 'fe3+_hematite-nano+goethite-fg',
    'fe3+_hematite.nano.BR34b2b', 'fe3+_hematite.lg.gr.br34c', 'fe3+_sulfate_jarosite_br34a2',
    'fe2+generic_broad_br60b', 'fe2+generic_vbroad_br20', 'fe2+fe3+_water_RTsludge',
    'fe2+_chlorite.clinochlor', 'fe2+_chlorite.Felow.clinochlor', 'fe2+_chlorite.thuringite',
    'copper_carbonate_azurite', 'fe3+copper-hydroxide_pitchlimonite', 'copper_carbonate_malachite',
    'copper_sulfate_bluefflor', 'copper_precipitate_greenslime', 'fe2+_olivine-lrg-gr',
    'fe2+_olivine-fine-gr', 'carbonate_rhodochrosite', 'fe2+generic_carbonate_siderite1',
    'fe2+generic_amphibole_riebeckite', 'fe3+fe2+_sulfate_coquimbite', 'fe3+fe2+_sulfate_copiapite',
    'copper_chrysocolla', 'ree_neodymium_oxide', 'ree_samarium_oxide', 'fe2+generic_axinite',
    'fe2+generic_staurolite', 'fe2+generic_almandine', 'fe2+_pyroxene_augite', 'fe2+_pyroxene.bronzite',
    'fe2+generic_sulfate_butlerite', 'fe2+_feldspar.bytownite', 'sulfide_copper_chalcopyrite',
    'fe2+_chromite', 'sulfide_cinnabar', 'copper_oxide_cuprite', 'fe3+mn_desert.varnish1',
    'fe3+mn_desert.varnish2', 'fe2+_pyroxene_enstatite', 'fe2+_pyroxene_hedenbergite', 'sulfate_lazurite',
    'fe3+_maghemite', 'magnetite', 'mn_oxide_pyrolusite', 'fe2+_feldspar_microcline', 'fe2+_feldspar_albite',
    'fe2+_feldspar_orthoclase', 'inosilicate_pectolite', 'mn2+_rhodonite', 'sulfur',
    'organic_vegetation-dry-grass-long', 'organic_vegetation-dry-grass-golden',
    'organic_vegetation-dry-wood', 'organic_plastic-tarp1', 'organic_plastic-vinyl',
    'organic_fiberglass-roofing', 'organic_plastic-polystyrene', 'organic_plastic-pete',
    'organic_plastic-pete2', 'organic_plastic-hdpe.1', 'organic_paint-1', 'organic_plastic-pete3',
    'organic_plastic-pete4', 'sulfate_kalun150c', 'sulfate_kalun250c', 'sulfate_kalun450c',
    'sulfate_naalun150c', 'sulfate_naalun300c', 'sulfate_naalun450c', 'sulfate_na82alun100c',
    'sulfate+kaolingrp_natroalun+dickite', 'sulfate_na63alun300c', 'sulfate_na40alun400c',
    'sulfate_alunNa03', 'sulfate_alunNa56450c', 'sulfate_alunNa78.450c', 'sulfate_alun35K65Na.low',
    'sulfate_alun73K27Na.low', 'sulfate_alun66K34Na.low', 'micagrp_muscovite-med-Al',
    'calcite.33+kaol.33+mus-AMXr2', 'micagrp_muscovite-medhigh-Al', 'micagrp_paragonite', 'micagrp_illite',
    'micagrp_illite.gds4', 'micagrp_muscovite-low-Al', 'micagrp_muscoviteFerich', 'kaolgrp_kaolinite_wxl',
    'kaolgrp_kaolinite_pxl', 'kaolgrp_halloysite', 'kaolgrp_nacrite', 'kaolgrp_dickite', 'sulfate_gypsum',
    'kaolin.5+smect.5', 'kaolin.3+smect.7', 'smectite_montmorillonite_na_highswelling',
    'smectite_montmorillonite_fe_swelling', 'smectite_montmorillonite_ca_swelling',
    'sioh_hydrated_basaltic_glass', 'sulfate_kieserite', 'sulfate_szomolnokite',
    'sulfate_szomolnokite_heated', 'perchlorate_mg', 'perchlorate_na', 'smectite_beidellite_gds123',
    'smectite_beidellite_gds124', 'sioh_chalcedony', 'hydroxide_diaspore', 'pyrophyllite',
    'kaol.75+pyroph.25', 'pyroph.5+mont0.5', 'pyroph.5+alunit.5', 'alunite+pyrophyl', 'pyroph+tr.musc',
    'musc+pyroph', 'alunite+musc+pyroph', 'alunite.5+kaol.5', 'kaol.75+alun.25', 'Kalun+kaol.intmx',
    'Na-alun+kaol.intmx', 'kaolin.5+muscov.medAl', 'kaolin.5+muscov.medhighAl', 'kaolin+musc.intimat',
    'musc+jarosite.intimat', 'sulfate-mix_gypsum+jar+illite.intmix', 'sulfate-mix_gyp+jar+musc.amix',
    'sulfate-mix_gyp+jar+musc+dick.amix', 'musc+gyp+jar+dick.amix', 'dick+musc+gyp+jar.amix',
    'alunite.5+musc.5', 'alunite.33+kaol.33+musc.33', 'muscovite+chlorite', 'smectite_ammonillsmec',
    'feldspar_buddingtonite_ammonium', 'feldspar_buddington.namont', 'feldspar_buddington.namont2',
    'sulfate_ammonalunite', 'sulfate_ammonjarosite', 'carbonate_dolomite', 'actinolite', 'amphibole',
    'micagrp_biotite', 'micagrp_biotite-phlogopite', 'chlorite-skarn', 'chlorite', 'prehnite+.50chlorite',
    'prehnite+.67chlorite', 'prehnite+.75chlorite', 'carbonate_aragonite', 'chlorite_clinochlore',
    'chlorite_clinochlore.nmnh83369', 'chlorite_clinochlore.fe.gds157', 'chlorite_clinochlore.fe.sc-cca-1',
    'chlorite_cookeite-car-1.a', 'chlorite_cookeite-car-1.c', 'chlorite_thuringite', 'epidote', 'hornblende',
    'sulfate_jarosite-Na', 'sulfate_jarosite-K', 'sulfate_jarosite-lowT', 'phlogopite', 'tremolite.or.talc',
    'talc.crsgrnd', 'talc.fngrnd', 'talc+calcite.parkcity', 'talc+carbonate.parkcity',
    'carbonate_calcite+0.2Ca-mont', 'carbonate_magnesite', 'carbonate_calcite',
    'carbonate_calcite+dolomite.5', 'carbonate_dolo+.5ca-mont', 'calcite.25+dolom.25+Na-mont.5',
    'carbonate_calcite.25+dolom.25+Ca-mont.5', 'carbonate_siderite', 'smectite_nontronite_swelling',
    'clay_hectorite', 'saponite.or.talc', 'sepiolite', 'calcite+0.2Na-mont', 'calcite+0.5Ca-mont',
    'carbonate_calcite+0.3muscovite', 'organic_drygrass+.17Na-mont', 'carbonate_dolomite.5+Na-mont.5',
    'carbonate_smectite_calcite.33+Ca-mont.67', 'carbonate_calcite+0.2kaolwxl',
    'carbonate_calcite0.7+kaol0.3', 'phyllosilicate.clintonite', 'palygorskite', 'zoisite', 'elbaite',
    'hydroxide_gibbsite', 'nitrate_niter', 'topaz', 'carbonate_rhodochrosite', 'carbonate_witherite',
    'prehnite', 'prehnite+muscovite', 'borate_pinnoite', 'polyhalite', 'rivadavite', 'howlite', 'ulexite',
    'white.crust.starkeyite', 'zeolite_analcime', 'hydroxide_brucite', 'chloride_carnallite',
    'borate_colemanite', 'datolite', 'hydrogrossular', 'micagrp_lepidolite', 'micagrp_margarite',
    'sulfate_mascagnite', 'sulfate_mirabilite-wet_soil', 'zeolite_natrolite', 'richterite',
    'serpentine_chrysotile.coarse-fibrous', 'serpentine_chrysotile.med-fine-fibrous',
    'serpentine_chrysotile.fine-fibrous', 'serpentine_cronstedtite', 'micagrp_illite.roscoelite',
    'carbonate_strontianite', 'sulfate_syngenite', 'chrysocolla', 'carbonate_azurite', 'carbonate_malachite',
    'cyanide-CdK', 'cyanide-NiK', 'cyanide-trihydrate', 'cyanide-KFe', 'cyanide-ZnK',
    'organic_plastic.grnhs.roof', 'organic_benzene+montswy', 'organic_trichlor+montswy',
    'organic_toluene+montswy', 'organic_unleaded.gas+montswy', 'organic_tce+montswy', 'zunyite',
    'sulfate-mix_gypsum.trace.dust+debris-WTC01-2', 'sulfate-mix_gypsum.trace.dust+debris-WTC01-28',
    'chrysotile.gypsum.wtc01-8', 'portlandite', 'nitrate_potassium', 'nitrate_sodium',
    'micagrp_vermiculite_GDS458', 'micagrp_vermiculite_ALB4SA00', 'micagrp_vermiculite_WS682',
    'micagrp_vermiculite_WS681', 'methane-gas-2.37um-experimental',
)

# Rules applied in order to the library entry name (e.g. "fe3+_hematite.fine.gr.gds76"). For a mixture,
# the family is that of the first mineral named (the most abundant one in these samples).
FAMILY_RULES = [
    # --- non-minerals
    (r"vegetation|drygrass", "vegetation"),
    (r"^organic_|plastic|paint|fiberglass|cyanide|methane|wtc01|portlandite", "artificiel"),
    (r"coating|desert\.varnish", "revetement"),
    (r"^sioh|chalcedony|opal", "silice_hydratee"),
    # --- mixtures: first mineral named
    (r"^calcite|^carbonate", "carbonate"),
    (r"^talc|^tremolite\.or\.talc|^saponite", "argile_fe_mg"),
    (r"^prehnite\+\.\d+chlorite", "argile_fe_mg"),
    (r"^kaol|^dick\+", "argile_al"),
    (r"^kalun\+kaol|^na-alun\+kaol|^alunite|^sulfate", "sulfate"),
    (r"^musc|^micagrp_vermiculite", None),          # mica, or vermiculite: decided in family_of()
    (r"^pyroph", "argile_al"),
    # --- Fe3+ and Fe2+
    (r"smectite_nontronite", "argile_fe_mg"),
    (r"fe3\+.*sulfate|fe2\+generic_sulfate", "sulfate"),
    (r"fe2\+generic_carbonate", "carbonate"),
    (r"fe2\+_chlor|fe2\+fe3\+_chlor|fe2\+generic_brd\.br36a_chlorite|fe2\+_chlorite", "argile_fe_mg"),
    (r"fe3\+copper", "autre_mineral"),
    (r"^fe3\+|^fe2\+_goeth|hematite|goethite|ferrihydrite|maghemite|^magnetite|amd\.assemb|rtsludge", "oxyde_fer"),
    (r"pyroxene|jadeite", "pyroxene"),
    (r"olivine", "olivine"),
    (r"feldspar[._](bytownite|microcline|albite|orthoclase)", "feldspath"),
    (r"^fe2\+generic|amphibole|actinolite|hornblende|richterite|cummingtonite|almandine|staurolite|axinite|"
     r"chromite|basalt", "mafique_autre"),
    # --- phyllosilicates
    (r"vermiculite", "argile_fe_mg"),
    (r"micagrp|phlogopite|clintonite|paragonite|illite|muscov", "mica"),
    (r"kaolgrp|kaolin|halloysite|dickite|nacrite|montmorillonite|beidellite|ammonillsmec|pyrophyllite|"
     r"gibbsite|diaspore", "argile_al"),
    (r"chlorite|serpentine|chrysotile|cronstedtite|talc|saponite|hectorite|sepiolite|palygorskite", "argile_fe_mg"),
    # --- other families
    (r"carbonate|siderite|magnesite|aragonite|rhodochrosite|witherite|strontianite|azurite|malachite", "carbonate"),
    (r"sulfate|gypsum|jarosite|alun|kieserite|szomolnokite|polyhalite|starkeyite|mirabilite|syngenite|mascagnite|"
     r"bluefflor|coquimbite|copiapite", "sulfate"),
    (r"perchlorate|chloride|carnallite|nitrate|borate|ulexite|howlite|rivadavite", "sel"),
]


def family_of(entry: str) -> str:
    """Family of an EMIT library entry: the first matching rule, `autre_mineral` if none matches."""
    name = entry.split("/")[-1].lower()
    for pattern, family in FAMILY_RULES:
        if re.search(pattern, name):
            if family is None:
                return "argile_fe_mg" if "vermiculite" in name else "mica"
            return family
    return "autre_mineral"


def emit_lookup_table() -> np.ndarray:
    """lut[EMIT mineral index] = rank of its family in ALL_FAMILIES (-1 = no mineral, index 0)."""
    rank = {family: i for i, family in enumerate(ALL_FAMILIES)}
    lut = np.full(len(EMIT_LIBRARY) + 1, -1, dtype=np.int16)
    lut[1:] = [rank[family_of(entry)] for entry in EMIT_LIBRARY]
    return lut
