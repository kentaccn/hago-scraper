"""What each test measures and why it gets ordered — English and 繁體中文.

Plain descriptions of the test itself, not interpretations of anyone's results.
Kept in code (rather than the database) precisely because it contains no patient
data: it is a reference table, the same for everybody.

Each entry: (English name, 中文名, what it is for in English, 用途)
"""

ANALYTES = {
    # --- inflammation ------------------------------------------------------
    "ESR": ("Erythrocyte sedimentation rate", "血沉降率",
            "How fast red cells settle in a tube. A slow, general marker of "
            "inflammation — it rises and falls over weeks, so it reflects a "
            "trend rather than today.",
            "紅血球在試管中下沉的速度。反映整體炎症的慢性指標，"
            "以週為單位上落，看的是趨勢而非當日狀況。"),
    "CRP": ("C-reactive protein", "C反應蛋白",
            "A protein the liver makes within hours of inflammation or "
            "infection. Faster-moving than ESR, so the two are read together.",
            "肝臟在發炎或感染後數小時內產生的蛋白。反應比血沉降率快，"
            "因此兩者通常一起解讀。"),
    "Calprotectin": ("Faecal calprotectin", "糞便鈣衛蛋白",
                     "Measured in stool. Distinguishes inflammation in the "
                     "bowel wall (as in IBD) from irritable bowel, and is used "
                     "to monitor known bowel disease.",
                     "從糞便樣本量度。用以分辨腸壁真正發炎（如發炎性腸病）"
                     "與腸易激綜合症，亦用於監察已知的腸道疾病。"),

    # --- red cells ---------------------------------------------------------
    "HGB": ("Haemoglobin", "血紅蛋白",
            "The oxygen-carrying protein in red cells. Low means anaemia.",
            "紅血球中負責運送氧氣的蛋白。偏低即貧血。"),
    "HCT": ("Haematocrit", "血球容積比",
            "The share of blood volume made up of red cells. Moves with "
            "haemoglobin.",
            "紅血球佔全血體積的比例，通常與血紅蛋白同升同降。"),
    "RBC": ("Red blood cell count", "紅血球計數",
            "How many red cells there are, regardless of their size.",
            "紅血球的數量，與其大小無關。"),
    "MCV": ("Mean cell volume", "平均紅血球體積",
            "The average size of a red cell. Small cells point toward iron "
            "deficiency or a thalassaemia trait; large cells toward B12 or "
            "folate.",
            "紅血球的平均大小。偏小提示缺鐵或地中海貧血特徵；"
            "偏大則提示缺乏維他命B12或葉酸。"),
    "MCH": ("Mean cell haemoglobin", "平均紅血球血紅蛋白量",
            "Average amount of haemoglobin per red cell. Read alongside MCV.",
            "每個紅血球平均含有的血紅蛋白量，與平均紅血球體積一併解讀。"),
    "MCHC": ("Mean cell haemoglobin concentration", "平均紅血球血紅蛋白濃度",
             "How concentrated the haemoglobin is inside each cell.",
             "紅血球內血紅蛋白的濃度。"),
    "RDW": ("Red cell distribution width", "紅血球大小分佈幅度",
            "How uneven the red cells are in size. A wide spread can be an "
            "early sign of a developing deficiency.",
            "紅血球大小的不均勻程度。分佈偏闊可能是營養缺乏的早期跡象。"),

    # --- white cells and platelets ----------------------------------------
    "WBC": ("White blood cell count", "白血球計數",
            "Total immune cells. Rises with infection, falls with some drugs "
            "including immune-suppressing treatment.",
            "免疫細胞總數。感染時上升；某些藥物（包括免疫抑制治療）會令其下降。"),
    "Neutrophil": ("Neutrophils", "嗜中性白血球",
                   "The white cells that deal mainly with bacterial infection.",
                   "主要對付細菌感染的白血球。"),
    "Lymphocyte": ("Lymphocytes", "淋巴細胞",
                   "White cells handling viral infection and immune memory.",
                   "負責對抗病毒感染及免疫記憶的白血球。"),
    "Monocyte": ("Monocytes", "單核細胞",
                 "White cells that clear debris and support chronic "
                 "inflammation.",
                 "負責清除殘骸、參與慢性發炎的白血球。"),
    "Eosinophil": ("Eosinophils", "嗜酸性白血球",
                   "Raised in allergy and parasitic infection.",
                   "在過敏及寄生蟲感染時上升。"),
    "Basophil": ("Basophils", "嗜鹼性白血球",
                 "The smallest white cell fraction; involved in allergy.",
                 "數量最少的白血球，與過敏反應有關。"),
    "NEU %": ("Neutrophil percentage", "嗜中性白血球百分比",
              "Neutrophils as a share of all white cells.",
              "嗜中性白血球佔白血球總數的百分比。"),
    "LYM %": ("Lymphocyte percentage", "淋巴細胞百分比",
              "Lymphocytes as a share of all white cells.",
              "淋巴細胞佔白血球總數的百分比。"),
    "MON %": ("Monocyte percentage", "單核細胞百分比",
              "Monocytes as a share of all white cells.",
              "單核細胞佔白血球總數的百分比。"),
    "EOS %": ("Eosinophil percentage", "嗜酸性白血球百分比",
              "Eosinophils as a share of all white cells.",
              "嗜酸性白血球佔白血球總數的百分比。"),
    "BAS %": ("Basophil percentage", "嗜鹼性白血球百分比",
              "Basophils as a share of all white cells.",
              "嗜鹼性白血球佔白血球總數的百分比。"),
    "PLT": ("Platelets", "血小板",
            "Cells that clot blood. They also rise as a by-product of "
            "inflammation.",
            "負責凝血的細胞；亦會因發炎而反應性上升。"),
    "MPV": ("Mean platelet volume", "平均血小板體積",
            "Average platelet size, a hint at how fast they are being made.",
            "血小板的平均大小，反映其生成速度。"),
    "MPV (Calculated)": ("Mean platelet volume (calculated)", "平均血小板體積（計算值）",
                         "As above, derived rather than measured directly.",
                         "同上，由計算得出而非直接量度。"),

    # --- kidney ------------------------------------------------------------
    "Creatinine": ("Creatinine", "肌酸酐",
                   "Muscle waste cleared by the kidneys — the main day-to-day "
                   "measure of kidney function.",
                   "由肌肉產生、經腎臟排走的廢物，是評估腎功能最常用的指標。"),
    "eGFR": ("Estimated glomerular filtration rate", "估算腎小球過濾率",
             "An estimate of how much blood the kidneys filter per minute, "
             "calculated from creatinine, age and sex.",
             "根據肌酸酐、年齡及性別估算腎臟每分鐘的過濾量。"),
    "Urea": ("Urea", "尿素",
             "Protein waste cleared by the kidneys; also affected by hydration "
             "and diet.",
             "蛋白質代謝後由腎臟排走的廢物，亦受水分及飲食影響。"),
    "Sodium": ("Sodium", "鈉",
               "The main salt in blood; governs fluid balance.",
               "血液中主要的鹽分，主宰體液平衡。"),
    "Potassium": ("Potassium", "鉀",
                  "Essential for heart rhythm and muscle function.",
                  "維持心律及肌肉功能的必需電解質。"),
    "Phosphate": ("Phosphate", "磷酸鹽",
                  "Mineral handled by the kidneys, tied to bone metabolism.",
                  "由腎臟調節的礦物質，與骨骼代謝相關。"),
    "Calcium": ("Calcium", "鈣",
                "Bone mineral, also needed for nerve and muscle function.",
                "骨骼的主要礦物質，亦為神經及肌肉功能所需。"),
    "Magnesium": ("Magnesium", "鎂",
                  "Mineral involved in muscle and nerve function.",
                  "參與肌肉及神經功能的礦物質。"),

    # --- liver -------------------------------------------------------------
    "ALT": ("Alanine aminotransferase", "丙氨酸轉氨酶",
            "A liver enzyme. Raised when liver cells are irritated — including "
            "by medication.",
            "肝臟酵素。肝細胞受損或受藥物影響時上升。"),
    "ALP": ("Alkaline phosphatase", "鹼性磷酸酶",
            "Enzyme from liver and bone. Read with the other liver tests to "
            "tell the two sources apart.",
            "來自肝臟及骨骼的酵素，需與其他肝功能指標一併解讀以分辨來源。"),
    "Albumin": ("Albumin", "白蛋白",
                "The main blood protein, made by the liver. Falls with chronic "
                "illness, inflammation or poor nutrition.",
                "由肝臟製造的主要血漿蛋白。慢性疾病、發炎或營養不良時下降。"),
    "Globulin": ("Globulin", "球蛋白",
                 "The other main protein group, including antibodies. Rises "
                 "with chronic immune activity.",
                 "另一組主要蛋白，包括抗體。長期免疫活動時上升。"),
    "Total Protein": ("Total protein", "總蛋白",
                      "Albumin and globulin together.",
                      "白蛋白與球蛋白的總和。"),
    "Bilirubin": ("Total bilirubin", "總膽紅素",
                  "Pigment from broken-down red cells, cleared by the liver.",
                  "紅血球分解後產生、由肝臟處理的色素。"),

    # --- immunology --------------------------------------------------------
    "Complement 3": ("Complement C3", "補體C3",
                     "Part of the immune cascade. Consumed — so falls — during "
                     "active immune-complex disease.",
                     "免疫級聯反應的一環。免疫複合物疾病活躍時會被消耗而下降。"),
    "Complement 4": ("Complement C4", "補體C4",
                     "As C3, another component of the same cascade.",
                     "與C3同屬補體系統的另一組成部分。"),
    "Anti-dsDNA": ("Anti-double-stranded DNA antibody", "抗雙鏈DNA抗體",
                   "An autoantibody used mainly to look for lupus.",
                   "自身抗體，主要用於檢查紅斑狼瘡。"),
    "RF": ("Rheumatoid factor", "類風濕因子",
           "An autoantibody associated with rheumatoid arthritis. Often "
           "negative in spondyloarthritis, which is itself informative.",
           "與類風濕關節炎相關的自身抗體。脊椎關節炎患者多為陰性，"
           "此陰性結果本身亦具參考價值。"),
    "ANA": ("Antinuclear antibody", "抗核抗體",
            "A screening autoantibody for connective tissue disease.",
            "篩查結締組織疾病的自身抗體。"),

    # --- iron --------------------------------------------------------------
    "Ferritin": ("Ferritin", "鐵蛋白",
                 "The body's iron store. Note it also rises with inflammation, "
                 "which can mask a genuine deficiency.",
                 "體內鐵質的儲存形式。發炎時亦會上升，可能掩蓋真正的缺鐵。"),
    "Iron": ("Serum iron", "血清鐵",
             "Iron circulating right now — varies through the day.",
             "當下在血液中循環的鐵質，日間有明顯波動。"),
    "TIBC": ("Total iron binding capacity", "總鐵結合力",
             "How much iron the blood could carry. Rises when stores are low.",
             "血液可攜帶鐵質的總能力。鐵質儲備不足時上升。"),
    "Iron Saturation": ("Transferrin saturation", "運鐵蛋白飽和度",
                        "The share of iron-carrying capacity actually in use — "
                        "the most useful single iron number.",
                        "實際被使用的鐵結合能力比例，是鐵質狀況最實用的單一指標。"),

    # --- metabolic ---------------------------------------------------------
    "HbA1c": ("Glycated haemoglobin", "糖化血紅蛋白",
              "Average blood sugar over roughly the last three months.",
              "反映過去約三個月的平均血糖水平。"),
    "HbA1c-IFCC": ("Glycated haemoglobin (IFCC units)", "糖化血紅蛋白（IFCC單位）",
                   "The same measurement reported on the international scale.",
                   "同一項檢查，以國際標準單位表示。"),
    "Glucose, spot": ("Spot glucose", "隨機血糖",
                      "Blood sugar at the moment of the draw, not fasting.",
                      "抽血當刻的血糖值，非空腹血糖。"),
    "Cholesterol": ("Total cholesterol", "總膽固醇",
                    "All cholesterol carried in blood.",
                    "血液中膽固醇的總量。"),
    "Triglyceride": ("Triglycerides", "三酸甘油脂",
                     "Blood fat, strongly affected by recent meals and alcohol.",
                     "血脂的一種，受近期飲食及酒精影響很大。"),
    "HDL-Cholesterol": ("HDL cholesterol", "高密度膽固醇",
                        "The protective fraction — higher is better.",
                        "具保護作用的膽固醇，愈高愈好。"),
    "LDL-Cholesterol": ("LDL cholesterol", "低密度膽固醇",
                        "The fraction that drives arterial disease — lower is "
                        "better.",
                        "導致動脈粥樣硬化的膽固醇，愈低愈好。"),
    "Non-HDL-Cholesterol": ("Non-HDL cholesterol", "非高密度膽固醇",
                            "Everything except the protective fraction; a "
                            "single summary of the harmful lipids.",
                            "除高密度膽固醇以外的部分，綜合反映有害血脂。"),
    "TSH": ("Thyroid stimulating hormone", "促甲狀腺激素",
            "The pituitary's signal to the thyroid — the first-line thyroid "
            "test.",
            "腦下垂體向甲狀腺發出的訊號，是甲狀腺功能的首選檢查。"),
}


def describe(analyte):
    """(en_name, zh_name, en_use, zh_use) or None if we have no entry."""
    return ANALYTES.get(analyte)
