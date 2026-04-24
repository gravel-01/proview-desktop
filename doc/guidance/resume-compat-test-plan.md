# 简历兼容性测试计划（面试官项目）

## 目标
- 统一覆盖简历文件上传、格式识别、OCR/直读提取、预览契约以及 Web/桌面共用后端行为。
- 把兼容性问题沉淀到可重复执行的自动化测试中，避免问题分散在多个 issue 无法追踪。

## 自动化覆盖范围
- `backend/tests/test_resume_text_extraction.py`
  - 直读路径：`.md`、`.docx`
  - OCR 必须路径：`.pdf` 在 OCR 不可用时应报错
  - 文本清洗：`unwrap_resume_text`
- `backend/tests/test_resume_compatibility_tracking.py`
  - 支持扩展名矩阵校验（OCR + 直读）
  - `.doc` 拒绝策略与提示文案校验
  - Windows GBK/CP936 编码下 OCR 日志安全输出校验
  - `/api/resume/analyze` 的 JSON 与 FormData 兼容契约校验
  - `/api/my-resumes` 预览字段序列化契约校验
- `backend/tests/run_resume_compat_suite.py`
  - 聚合执行上述用例
  - 自动输出 JSON + Markdown 报告

## 手工补充维度（建议）
- 文件来源：WPS / Word / Pages / 手机扫描件 / 招聘网站下载
- 文件特征：双栏、表格、图片混排、超大文件、中文文件名、空格文件名
- 运行环境：Web + 桌面；Windows + macOS + Linux

## 执行命令
```powershell
cd D:\proview-desktop\proview-desktop\backend
python -m unittest tests.test_resume_compatibility_tracking
python tests\run_resume_compat_suite.py
```

## 报告产物
- `backend/tests/artifacts/resume-compat-results.json`
- `backend/tests/artifacts/resume-compat-report.md`

## 失败后排查顺序
1. 先看 `resume-compat-results.json` 里的 `failed_items`。
2. 再看 `resume-compat-report.md` 里的 traceback。
3. 最后结合 issue 模板补充：文件格式、来源、运行环境、复现步骤、报错截图。

