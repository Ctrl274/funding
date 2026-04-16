## 技术偏好

- Python 项目: venv 虚拟环境，pip 管理依赖，requirements.txt 锁版本
- Node.js 项目: npm，CommonJS (不用 ESM)，不用 TypeScript
- 数据库优先 SQLite，除非有明确的并发需求
- 新项目默认用 Python，除非场景明确更适合 Node.js
- 不用框架能解决的就不引入框架

## 报告与分析
- 分析类内容必须让AI读真实源数据后生成,禁止硬编码模板文字拼统计数字
- 报告质量标准:能直接拿去跟团队开会用,不是"格式对了就行"
- 交付物默认放当前目录,不用问
- 有多个版本时直接给最新最好的,不要问"你要哪个"

## 测试规范
- 每次跑测试必须生成 HTML 测试报告（`--html=... --self-contained-html`）
- 每次新增/修改测试用例后，同步更新对应的测试用例文档
- API 测试和 UI 测试严格分目录：
  - 报告：`reports/api/`（API 测试报告）、`reports/web/`（UI 测试报告和截图）
  - 文档：`docs/api/`（API 接口文档、测试用例）、`docs/web/`（UI 测试用例）
  - 代码：`tests/spot/`（API 自动化）、`tests/web/`（UI 自动化）
- 测试报告命名清晰：`api_test_report.html`、`spot_ui_report.html` 等

## Skill / 工具维护

- 修改 skill 文件（如 md2pdf.py）后，改的就是源文件，直接生效，不需要额外"保存"步骤
- 生成 markdown 准备转 PDF 时，**禁止使用特殊 Unicode 字符**（如 ✅❌→←┃┌└▶ 等 emoji 和 box-drawing 字符），直接用 ASCII 替代（、[X]、->、<-、|），从源头避免字体渲染问题
- md2pdf 代码块和行内代码必须用 CJK 字体（不用 Courier），否则中文变黑块
- md2pdf 的 Preformatted 不解析 XML，代码块内容不做 escape_xml

## 自我进化

- 遇到值得记住的经验、偏好、教训，主动存到 memory
- 会话开始时回顾已有 memory
- 保持 memory 精简，同类合并，过时的删掉
- **memory 更新必须及时** — 每次关键决策/新增文档/参数变更/经验教训时立即同步，不等用户提醒

## Skill routing

When the user's request matches an available skill, ALWAYS invoke it using the Skill
tool as your FIRST action. Do NOT answer directly, do NOT use other tools first.
The skill has specialized workflows that produce better results than ad-hoc answers.

Key routing rules:
- Product ideas, "is this worth building", brainstorming -> invoke office-hours
- Bugs, errors, "why is this broken", 500 errors -> invoke investigate
- Ship, deploy, push, create PR -> invoke ship
- QA, test the site, find bugs -> invoke qa
- Code review, check my diff -> invoke review
- Update docs after shipping -> invoke document-release
- Weekly retro -> invoke retro
- Design system, brand -> invoke design-consultation
- Visual audit, design polish -> invoke design-review
- Architecture review -> invoke plan-eng-review
- Save progress, checkpoint, resume -> invoke checkpoint
- Code quality, health check -> invoke health

# 注意
- 每次工具调用后先确认结果再继续，避免长链路中断后状态不一致。
- 不涉及到删除操作 不需要我确认