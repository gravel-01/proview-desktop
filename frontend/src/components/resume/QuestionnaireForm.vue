<template>
  <div class="pv-qf">
    <div class="pv-qf__bg" aria-hidden="true">
      <div class="pv-qf__orb pv-qf__orb--a" />
      <div class="pv-qf__orb pv-qf__orb--b" />
      <div class="pv-qf__dots" />
    </div>

    <div class="pv-qf__wrap">
      <div class="pv-qf__card">
        <!-- Progress bar -->
        <div class="pv-qf__progress">
          <div class="pv-qf__progressRow">
            <span class="pv-qf__stepText">
              Step <span class="pv-qf__stepStrong">{{ store.currentStep }}</span> / 7
            </span>
          </div>
          <div class="pv-qf__bar" role="progressbar" :aria-valuenow="store.currentStep" aria-valuemin="1" aria-valuemax="7">
            <div class="pv-qf__barFill" :style="{ width: `${(store.currentStep / 7) * 100}%` }" />
            <div class="pv-qf__barGlow" :style="{ left: `${(store.currentStep / 7) * 100}%` }" aria-hidden="true" />
          </div>
        </div>

        <form class="pv-qf__form" @submit.prevent>
          <!-- Step 1: Target Position -->
          <Transition name="pv-qf-swap" mode="out-in">
            <div v-if="store.currentStep === 1" key="s1" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 1：目标岗位（决定简历方向）</h2>
              <div class="pv-qf__grid">
                <div class="pv-qf__field">
                  <label class="pv-qf__label">你想申请的岗位是？</label>
                  <input v-model="store.formData.targetRole" type="text" class="pv-qf__input" placeholder="如：前端开发工程师" />
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">目标行业</label>
                  <input type="text" class="pv-qf__input" placeholder="如：互联网, AI（逗号分隔）" @change="(e: any) => store.formData.targetIndustries = e.target.value.split(',')" />
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">目标公司类型</label>
                  <select v-model="store.formData.targetCompanyType" class="pv-qf__input">
                    <option>大厂（如互联网头部公司）</option>
                    <option>中型公司</option>
                    <option>初创公司</option>
                    <option>外企</option>
                    <option>不确定</option>
                  </select>
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">当前工作经验</label>
                  <select v-model="store.formData.currentExperienceBase" class="pv-qf__input">
                    <option>应届生 / 在校</option>
                    <option>0-1年</option>
                    <option>1-3年</option>
                    <option>3-5年</option>
                    <option>5年以上</option>
                  </select>
                </div>
              </div>
            </div>

            <!-- Step 2: Optimization Goals -->
            <div v-else-if="store.currentStep === 2" key="s2" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 2：本次优化目标（非常关键）</h2>
              <div class="pv-qf__field">
                <label class="pv-qf__label">你希望这次简历优化重点是？(最多选3项，逗号分隔)</label>
                <input type="text" class="pv-qf__input" placeholder="如：提高简历通过率, 突出项目成果" @change="(e: any) => store.formData.optimizationGoals = e.target.value.split(',')" />
              </div>
              <div class="pv-qf__field">
                <label class="pv-qf__label">是否有明确岗位 JD？</label>
                <div class="pv-qf__choiceRow">
                  <label class="pv-qf__choice"><input type="radio" v-model="store.formData.hasJd" :value="true" /> 有</label>
                  <label class="pv-qf__choice"><input type="radio" v-model="store.formData.hasJd" :value="false" /> 没有</label>
                </div>
              </div>
              <div v-if="store.formData.hasJd" class="pv-qf__field">
                <label class="pv-qf__label">JD 内容</label>
                <textarea v-model="store.formData.jdContent" rows="4" class="pv-qf__input pv-qf__textarea" />
              </div>
            </div>

            <!-- Step 3: Work Experience -->
            <div v-else-if="store.currentStep === 3" key="s3" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 3：工作经历（核心模块）</h2>

              <div v-for="(exp) in store.formData.workExperiences" :key="exp.id" class="pv-qf__panel">
                <button type="button" @click="store.removeWorkExperience(exp.id)" class="pv-qf__dangerBtn">删除此段</button>

                <div class="pv-qf__grid pv-qf__grid--2">
                  <div class="pv-qf__field">
                    <label class="pv-qf__label">公司名称</label>
                    <input v-model="exp.companyName" type="text" class="pv-qf__input" />
                  </div>
                  <div class="pv-qf__field">
                    <label class="pv-qf__label">职位名称</label>
                    <input v-model="exp.jobTitle" type="text" class="pv-qf__input" />
                  </div>
                  <div class="pv-qf__field">
                    <label class="pv-qf__label">开始时间</label>
                    <input v-model="exp.startDate" type="text" class="pv-qf__input" placeholder="YYYY.MM" />
                  </div>
                  <div class="pv-qf__field">
                    <label class="pv-qf__label">结束时间</label>
                    <input v-model="exp.endDate" type="text" class="pv-qf__input" placeholder="YYYY.MM" />
                  </div>
                  <div class="pv-qf__field">
                    <label class="pv-qf__label">是否管理岗</label>
                    <select v-model="exp.isManagement" class="pv-qf__input">
                      <option :value="true">是</option>
                      <option :value="false">否</option>
                    </select>
                  </div>
                </div>

                <div v-if="exp.isManagement" class="pv-qf__field mt-4">
                  <label class="pv-qf__label">管理人数</label>
                  <input v-model.number="exp.managementCount" type="number" class="pv-qf__input" />
                </div>

                <div class="mt-4">
                  <label class="pv-qf__label mb-2">是否有明确成果？</label>
                  <div class="pv-qf__choiceRow pv-qf__choiceRow--wrap">
                    <label class="pv-qf__choice"><input type="radio" v-model="exp.hasSpecificOutcome" value="YES_DATA" /> 有明确数据成果</label>
                    <label class="pv-qf__choice"><input type="radio" v-model="exp.hasSpecificOutcome" value="YES_NO_DATA" /> 有成果但没有数据</label>
                    <label class="pv-qf__choice"><input type="radio" v-model="exp.hasSpecificOutcome" value="NOT_SURE" /> 不确定</label>
                  </div>

                  <div v-if="exp.hasSpecificOutcome === 'YES_DATA'" class="pv-qf__subPanel">
                    <label class="pv-qf__label">成果提升幅度</label>
                    <input v-model="exp.outcomeImprovement" type="text" class="pv-qf__input" placeholder="如：转化率提升25%" />
                  </div>
                  <div v-else-if="exp.hasSpecificOutcome === 'YES_NO_DATA'" class="pv-qf__subPanel">
                    <label class="pv-qf__label">你的工作带来的影响是？</label>
                    <div class="pv-qf__checkList">
                      <label class="pv-qf__choice"><input type="checkbox" v-model="exp.implicitOutcomes" value="提升了效率"> 提升了效率</label>
                      <label class="pv-qf__choice"><input type="checkbox" v-model="exp.implicitOutcomes" value="减少了错误"> 减少了错误</label>
                      <label class="pv-qf__choice"><input type="checkbox" v-model="exp.implicitOutcomes" value="优化了流程"> 优化了流程</label>
                    </div>
                  </div>
                </div>
              </div>

              <button type="button" @click="store.addWorkExperience" class="pv-qf__addBtn">
                + 添加一段经历
              </button>
            </div>

            <!-- Step 4: Skills -->
            <div v-else-if="store.currentStep === 4" key="s4" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 4：技能 (ATS优化核心)</h2>
              <div class="pv-qf__panel">
                <button type="button" @click="store.formData.skills.push({name: '', level: '了解'})" class="pv-qf__linkBtn">+ 添加技能</button>
                <div v-for="(skill, idx) in store.formData.skills" :key="idx" class="pv-qf__row">
                  <input v-model="skill.name" type="text" placeholder="技能名称" class="pv-qf__input pv-qf__input--grow" />
                  <select v-model="skill.level" class="pv-qf__input">
                    <option value="了解">了解</option>
                    <option value="熟悉">熟悉</option>
                    <option value="熟练">熟练</option>
                    <option value="精通">精通</option>
                  </select>
                  <button type="button" @click="store.formData.skills.splice(idx, 1)" class="pv-qf__dangerBtnInline">删除</button>
                </div>
              </div>
            </div>

            <!-- Step 5: Education -->
            <div v-else-if="store.currentStep === 5" key="s5" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 5：教育背景</h2>
              <div class="pv-qf__grid">
                <div class="pv-qf__field">
                  <label class="pv-qf__label">学校</label>
                  <input v-model="store.formData.education.school" type="text" class="pv-qf__input" />
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">学历</label>
                  <select v-model="store.formData.education.degree" class="pv-qf__input">
                    <option value="专科">专科</option>
                    <option value="本科">本科</option>
                    <option value="硕士">硕士</option>
                    <option value="博士">博士</option>
                  </select>
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">专业</label>
                  <input v-model="store.formData.education.major" type="text" class="pv-qf__input" />
                </div>
                <div class="pv-qf__field">
                  <label class="pv-qf__label">是否有亮点 (逗号分隔)</label>
                  <input type="text" class="pv-qf__input" placeholder="如：奖学金, 排名前10%" @change="(e: any) => store.formData.education.highlights = e.target.value.split(',')" />
                </div>
              </div>
            </div>

            <!-- Step 6: Style & Strategy -->
            <div v-else-if="store.currentStep === 6" key="s6" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 6：风格与优化策略（AI生成控制）</h2>
              <div class="pv-qf__field">
                <label class="pv-qf__label">你希望简历风格是？</label>
                <select v-model="store.formData.resumeStyle" class="pv-qf__input">
                  <option value="简洁专业（外企风格）">简洁专业（外企风格）</option>
                  <option value="成果导向（互联网推荐）">成果导向（互联网推荐）</option>
                  <option value="技术深度（技术岗）">技术深度（技术岗）</option>
                  <option value="内容全面（传统行业）">内容全面（传统行业）</option>
                </select>
              </div>
              <div class="pv-qf__field">
                <label class="pv-qf__label">是否需要以下优化？ (逗号分隔)</label>
                <input type="text" class="pv-qf__input" placeholder="如：强化关键词匹配, 自动生成英文简历" @change="(e: any) => store.formData.optimizationStrategies = e.target.value.split(',')" />
              </div>
            </div>

            <!-- Step 7: Additional Info -->
            <div v-else key="s7" class="pv-qf__step">
              <h2 class="pv-qf__h2">Step 7：附加信息（可选但加分）</h2>
              <div class="pv-qf__field">
                <label class="pv-qf__label">你还有哪些补充优势？</label>
                <textarea v-model="store.formData.additionalAdvantages" rows="4" placeholder="如：开源项目、技术博客、证书、副业经历..." class="pv-qf__input pv-qf__textarea" />
              </div>
            </div>
          </Transition>

          <!-- Bottom controls -->
          <div class="pv-qf__footer">
            <button type="button" @click="store.prevStep" :disabled="store.currentStep === 1" class="pv-qf__btn pv-qf__btn--prev">
              上一步
            </button>

            <button
              type="button"
              v-if="store.currentStep < 7"
              @click="store.nextStep"
              class="pv-qf__btn pv-qf__btn--next"
            >
              <span class="pv-qf__btnGlow" aria-hidden="true" />
              下一步
            </button>
            <button
              type="button"
              v-else
              @click="$emit('submit-questionnaire', store.formData)"
              class="pv-qf__btn pv-qf__btn--next"
            >
              <span class="pv-qf__btnGlow" aria-hidden="true" />
              提交问卷并优化
            </button>
          </div>
        </form>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useResumeQuestionnaireStore } from '../../stores/resumeQuestionnaire';

const store = useResumeQuestionnaireStore();
if (store.formData.workExperiences.length === 0) store.addWorkExperience();

defineEmits(['submit-questionnaire']);
</script>

<style scoped>
@reference "tailwindcss";

.pv-qf {
  position: relative;
  min-height: 100vh;
  overflow: hidden;
  padding: 28px 14px;
  background: linear-gradient(to bottom right, rgba(240, 249, 255, 0.4), rgba(255, 255, 255, 1), rgba(239, 246, 255, 0.3));
}

.pv-qf__bg {
  pointer-events: none;
  position: absolute;
  inset: 0;
}

.pv-qf__orb {
  position: absolute;
  border-radius: 9999px;
  filter: blur(64px);
}

.pv-qf__orb--a {
  left: -220px;
  top: -220px;
  width: 600px;
  height: 600px;
  background: radial-gradient(circle, rgba(224, 242, 254, 0.22), transparent 65%);
  animation: pv-qf-orb-a 30s ease-in-out infinite;
}

.pv-qf__orb--b {
  right: -200px;
  bottom: -220px;
  width: 500px;
  height: 500px;
  background: radial-gradient(circle, rgba(219, 234, 254, 0.18), transparent 65%);
  animation: pv-qf-orb-b 28s ease-in-out infinite;
}

@keyframes pv-qf-orb-a {
  0%,
  100% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(0, 30px, 0) scale(1.1); }
}

@keyframes pv-qf-orb-b {
  0%,
  100% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(0, -25px, 0) scale(1.15); }
}

.pv-qf__dots {
  position: absolute;
  inset: 0;
  opacity: 0.005;
  background-image: radial-gradient(circle, #111827 0.7px, transparent 0.7px);
  background-size: 60px 60px;
}

.pv-qf__wrap {
  position: relative;
  z-index: 1;
  margin: 0 auto;
  max-width: 900px;
  display: flex;
  justify-content: center;
}

.pv-qf__card {
  width: min(720px, 92vw);
  border-radius: 24px;
  border: 1px solid rgba(229, 231, 235, 0.6);
  background:
    linear-gradient(
      135deg,
      rgba(255, 255, 255, 0.9) 0%,
      rgba(224, 242, 254, 0.25) 30%,
      rgba(219, 234, 254, 0.25) 70%,
      rgba(255, 255, 255, 0.9) 100%
    );
  box-shadow:
    0 18px 50px rgba(15, 23, 42, 0.08),
    0 30px 70px rgba(59, 130, 246, 0.08),
    0 0 100px rgba(147, 197, 253, 0.05);
  backdrop-filter: blur(18px);
  -webkit-backdrop-filter: blur(18px);
  padding: 22px;
}

@media (min-width: 768px) {
  .pv-qf__card { padding: 44px; }
}

.pv-qf__progress {
  margin-bottom: 22px;
}

.pv-qf__progressRow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.pv-qf__stepText {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
}
.pv-qf__stepStrong {
  color: #2563eb;
  font-weight: 800;
}

.pv-qf__bar {
  position: relative;
  height: 4px;
  border-radius: 9999px;
  background: rgba(243, 244, 246, 1);
  overflow: hidden;
}
.pv-qf__barFill {
  height: 100%;
  border-radius: 9999px;
  background: linear-gradient(90deg, #38bdf8, #3b82f6);
  transition: width 0.6s ease;
}
.pv-qf__barGlow {
  position: absolute;
  top: 50%;
  width: 14px;
  height: 14px;
  transform: translate3d(-50%, -50%, 0);
  border-radius: 9999px;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.35), transparent 60%);
  animation: pv-qf-glow-breathe 2.6s ease-in-out infinite;
}
@keyframes pv-qf-glow-breathe {
  0%,
  100% { opacity: 0.45; transform: translate3d(-50%, -50%, 0) scale(0.9); }
  50% { opacity: 0.85; transform: translate3d(-50%, -50%, 0) scale(1.1); }
}

.pv-qf__h2 {
  font-size: 20px;
  line-height: 1.6;
  font-weight: 700;
  color: #111827;
  margin-bottom: 14px;
}

.pv-qf__form { display: flex; flex-direction: column; gap: 18px; }
.pv-qf__step { min-height: 380px; }

.pv-qf__grid { display: grid; gap: 14px; }
.pv-qf__grid--2 { grid-template-columns: 1fr; }
@media (min-width: 768px) {
  .pv-qf__grid { grid-template-columns: 1fr 1fr; }
  .pv-qf__grid--2 { grid-template-columns: 1fr 1fr; }
}

.pv-qf__field { display: flex; flex-direction: column; gap: 6px; }
.pv-qf__label {
  font-size: 14px;
  font-weight: 600;
  color: #374151;
}

.pv-qf__input {
  width: 100%;
  border-radius: 12px;
  border: 1px solid rgba(229, 231, 235, 1);
  background: rgba(255, 255, 255, 0.7);
  padding: 10px 12px;
  font-size: 14px;
  color: #111827;
  box-shadow: 0 1px 8px rgba(15, 23, 42, 0.04);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}
.pv-qf__input:focus {
  outline: none;
  border-color: rgba(59, 130, 246, 1);
  box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.12);
  background: rgba(255, 255, 255, 0.85);
}
.pv-qf__input--grow { flex: 1; }
.pv-qf__textarea { min-height: 120px; resize: vertical; }

.pv-qf__choiceRow {
  display: flex;
  gap: 16px;
  align-items: center;
  margin-top: 4px;
  color: #374151;
  font-size: 14px;
}
.pv-qf__choiceRow--wrap { flex-wrap: wrap; }
.pv-qf__choice { display: inline-flex; align-items: center; gap: 8px; }
.pv-qf__choice input { accent-color: #3b82f6; }

.pv-qf__panel {
  position: relative;
  border-radius: 16px;
  border: 1px solid rgba(229, 231, 235, 0.85);
  background: rgba(255, 255, 255, 0.6);
  padding: 16px;
  box-shadow: 0 10px 26px rgba(15, 23, 42, 0.06);
}
.pv-qf__subPanel {
  margin-top: 12px;
  border-radius: 12px;
  border: 1px solid rgba(186, 230, 253, 1);
  background: linear-gradient(135deg, rgba(224, 242, 254, 0.4), rgba(255, 255, 255, 0.7));
  padding: 12px;
}
.pv-qf__checkList { margin-top: 8px; display: flex; flex-direction: column; gap: 8px; color: #6b7280; }

.pv-qf__dangerBtn {
  position: absolute;
  top: 12px;
  right: 12px;
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  transition: color 0.2s ease, transform 0.2s ease;
}
.pv-qf__dangerBtn:hover { color: #111827; transform: translateY(-1px); }
.pv-qf__dangerBtnInline {
  font-size: 12px;
  font-weight: 600;
  color: #6b7280;
  padding: 0 8px;
  transition: color 0.2s ease;
}
.pv-qf__dangerBtnInline:hover { color: #111827; }

.pv-qf__addBtn {
  width: 100%;
  padding: 12px 14px;
  border-radius: 14px;
  border: 2px dashed rgba(209, 213, 219, 1);
  background: rgba(255, 255, 255, 0.55);
  color: #6b7280;
  font-weight: 600;
  transition: border-color 0.2s ease, color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}
.pv-qf__addBtn:hover {
  border-color: rgba(59, 130, 246, 1);
  color: #1d4ed8;
  background: rgba(255, 255, 255, 0.75);
  transform: translateY(-1px);
}

.pv-qf__row { display: flex; gap: 10px; align-items: center; margin-top: 10px; flex-wrap: wrap; }
.pv-qf__linkBtn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  font-weight: 700;
  color: #2563eb;
  margin-bottom: 8px;
  transition: color 0.2s ease, transform 0.2s ease;
}
.pv-qf__linkBtn:hover { color: #1d4ed8; transform: translateY(-1px); }

.pv-qf__footer {
  margin-top: 12px;
  padding-top: 16px;
  border-top: 1px solid rgba(229, 231, 235, 0.6);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.pv-qf__btn {
  border-radius: 12px;
  padding: 12px 18px;
  font-size: 14px;
  font-weight: 700;
  transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease, color 0.2s ease;
}
.pv-qf__btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  transform: none;
  box-shadow: none;
}
.pv-qf__btn--prev {
  background: #ffffff;
  border: 1px solid rgba(229, 231, 235, 1);
  color: #374151;
}
.pv-qf__btn--prev:not(:disabled):hover {
  background: rgba(240, 249, 255, 1);
  border-color: rgba(186, 230, 253, 1);
  color: #1d4ed8;
  transform: translateY(-2px);
}
.pv-qf__btn--next {
  position: relative;
  overflow: hidden;
  color: #ffffff;
  background: linear-gradient(135deg, #60a5fa 0%, #3b82f6 100%);
  box-shadow: 0 6px 20px rgba(59, 130, 246, 0.25);
}
.pv-qf__btn--next:not(:disabled):hover {
  transform: translateY(-3px) scale(1.04);
  box-shadow: 0 10px 30px rgba(59, 130, 246, 0.35);
}
.pv-qf__btnGlow {
  position: absolute;
  inset: -40%;
  background: radial-gradient(circle, rgba(59, 130, 246, 0.25), transparent 55%);
  opacity: 0.35;
  animation: pv-qf-btn-breathe 3s ease-in-out infinite;
  pointer-events: none;
}
@keyframes pv-qf-btn-breathe {
  0%,
  100% { opacity: 0.3; transform: scale(0.95); }
  50% { opacity: 0.6; transform: scale(1.05); }
}

.pv-qf-swap-enter-active,
.pv-qf-swap-leave-active {
  transition: opacity 0.3s ease, transform 0.3s ease;
}
.pv-qf-swap-enter-from { opacity: 0; transform: translate3d(30px, 0, 0); }
.pv-qf-swap-leave-to { opacity: 0; transform: translate3d(-30px, 0, 0); }

@media (max-width: 640px) {
  .pv-qf__footer {
    flex-direction: column-reverse;
    align-items: stretch;
  }
  .pv-qf__btn { width: 100%; }
}

@media (prefers-reduced-motion: reduce) {
  .pv-qf__orb--a,
  .pv-qf__orb--b,
  .pv-qf__barGlow,
  .pv-qf__btnGlow {
    animation: none !important;
  }
}
</style>

