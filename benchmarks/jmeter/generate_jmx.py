#!/usr/bin/env python3
"""Emit dating-api-benchmark.jmx (Apache JMeter 5.6). Run from repo: python3 benchmarks/jmeter/generate_jmx.py"""

from __future__ import annotations

from pathlib import Path

OUT = Path(__file__).resolve().parent / "dating-api-benchmark.jmx"

# Two thread groups: cheap health probes + realistic multi-endpoint bot sessions.
# Discovery writes use RegexExtractor + JSR223 for 22% like / 78% skip when a card exists.
JMX = r'''<?xml version="1.0" encoding="UTF-8"?>
<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">
  <hashTree>
    <TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="dating-api-benchmark" enabled="true">
      <stringProp name="TestPlan.comments">Realistic load: health + profile/me + incoming-likes + discovery next then weighted like/skip. Tune -Japi.* -Jjourney.* -Jhealth.* -JlikeRatio -Jbot.secret</stringProp>
      <boolProp name="TestPlan.functional_mode">false</boolProp>
      <boolProp name="TestPlan.serialize_threadgroups">false</boolProp>
      <boolProp name="TestPlan.tearDown_on_shutdown">true</boolProp>
      <elementProp name="TestPlan.user_defined_variables" elementType="Arguments" guiclass="ArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
        <collectionProp name="Arguments.arguments"/>
      </elementProp>
      <stringProp name="TestPlan.user_define_classpath"></stringProp>
    </TestPlan>
    <hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="01 Health probes" enabled="true">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <stringProp name="LoopController.loops">${__P(health.loops,40)}</stringProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">${__P(health.users,4)}</stringProp>
        <stringProp name="ThreadGroup.ramp_time">${__P(health.ramp,4)}</stringProp>
        <boolProp name="ThreadGroup.scheduler">false</boolProp>
        <stringProp name="ThreadGroup.duration"></stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
        <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
      </ThreadGroup>
      <hashTree>
        <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="GET /health" enabled="true">
          <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="User Defined Variables" enabled="true">
            <collectionProp name="Arguments.arguments"/>
          </elementProp>
          <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
          <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
          <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
          <stringProp name="HTTPSampler.contentEncoding"></stringProp>
          <stringProp name="HTTPSampler.path">/health</stringProp>
          <stringProp name="HTTPSampler.method">GET</stringProp>
          <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
          <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
          <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
          <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
          <boolProp name="HTTPSampler.postBodyRaw">false</boolProp>
        </HTTPSamplerProxy>
        <hashTree>
          <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="JSON has ok status" enabled="true">
            <collectionProp name="Asserion.test_strings">
              <stringProp name="0">&quot;status&quot;:&quot;ok&quot;</stringProp>
            </collectionProp>
            <stringProp name="Assertion.custom_message"></stringProp>
            <stringProp name="Assertion.test_field">Assertion.response_data</stringProp>
            <boolProp name="Assertion.assume_success">false</boolProp>
            <intProp name="Assertion.test_type">16</intProp>
          </ResponseAssertion>
          <hashTree/>
        </hashTree>
      </hashTree>
      <ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="02 Realistic bot session" enabled="true">
        <stringProp name="ThreadGroup.on_sample_error">continue</stringProp>
        <elementProp name="ThreadGroup.main_controller" elementType="LoopController" guiclass="LoopControlPanel" testclass="LoopController" testname="Loop Controller" enabled="true">
          <boolProp name="LoopController.continue_forever">false</boolProp>
          <stringProp name="LoopController.loops">${__P(journey.loops,12)}</stringProp>
        </elementProp>
        <stringProp name="ThreadGroup.num_threads">${__P(journey.users,35)}</stringProp>
        <stringProp name="ThreadGroup.ramp_time">${__P(journey.ramp,25)}</stringProp>
        <boolProp name="ThreadGroup.scheduler">false</boolProp>
        <stringProp name="ThreadGroup.duration"></stringProp>
        <stringProp name="ThreadGroup.delay"></stringProp>
        <boolProp name="ThreadGroup.same_user_on_next_iteration">true</boolProp>
      </ThreadGroup>
      <hashTree>
        <CSVDataSet guiclass="TestBeanGUI" testclass="CSVDataSet" testname="viewers.csv" enabled="true">
          <stringProp name="filename">${__P(csv.file,viewers.csv)}</stringProp>
          <stringProp name="fileEncoding">UTF-8</stringProp>
          <stringProp name="variableNames">telegram_id</stringProp>
          <boolProp name="ignoreFirstLine">true</boolProp>
          <stringProp name="delimiter">,</stringProp>
          <boolProp name="quotedData">false</boolProp>
          <boolProp name="recycle">true</boolProp>
          <boolProp name="stopThread">false</boolProp>
          <stringProp name="shareMode">shareMode.all</stringProp>
        </CSVDataSet>
        <hashTree/>
        <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="Bot auth + JSON" enabled="true">
          <collectionProp name="HeaderManager.headers">
            <elementProp name="" elementType="Header">
              <stringProp name="Header.name">Content-Type</stringProp>
              <stringProp name="Header.value">application/json</stringProp>
            </elementProp>
            <elementProp name="" elementType="Header">
              <stringProp name="Header.name">X-Bot-Secret</stringProp>
              <stringProp name="Header.value">${__P(bot.secret,change-me-in-production)}</stringProp>
            </elementProp>
          </collectionProp>
        </HeaderManager>
        <hashTree/>
        <TransactionController guiclass="TransactionControllerGui" testclass="TransactionController" testname="session" enabled="true">
          <boolProp name="TransactionController.includeTimers">true</boolProp>
          <boolProp name="TransactionController.parent">false</boolProp>
        </TransactionController>
        <hashTree>
          <UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="think before profile" enabled="true">
            <stringProp name="ConstantTimer.delay">${__P(think.ms.min,15)}</stringProp>
            <stringProp name="RandomTimer.range">${__P(think.ms.range,120)}</stringProp>
          </UniformRandomTimer>
          <hashTree/>
          <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="POST /profile/me" enabled="true">
            <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
            <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="Body" enabled="true">
              <collectionProp name="Arguments.arguments">
                <elementProp name="" elementType="HTTPArgument">
                  <boolProp name="HTTPArgument.always_encode">false</boolProp>
                  <stringProp name="Argument.value">{"telegram_id":${telegram_id}}</stringProp>
                  <stringProp name="Argument.metadata">=</stringProp>
                </elementProp>
              </collectionProp>
            </elementProp>
            <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
            <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
            <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
            <stringProp name="HTTPSampler.path">/profile/me</stringProp>
            <stringProp name="HTTPSampler.method">POST</stringProp>
            <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
            <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          </HTTPSamplerProxy>
          <hashTree>
            <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="profile 200" enabled="true">
              <collectionProp name="Asserion.test_strings">
                <stringProp name="0">200</stringProp>
              </collectionProp>
              <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
              <boolProp name="Assertion.assume_success">false</boolProp>
              <intProp name="Assertion.test_type">8</intProp>
            </ResponseAssertion>
            <hashTree/>
          </hashTree>
          <UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="think before inbox" enabled="true">
            <stringProp name="ConstantTimer.delay">${__P(think.ms.min,15)}</stringProp>
            <stringProp name="RandomTimer.range">${__P(think.ms.range,120)}</stringProp>
          </UniformRandomTimer>
          <hashTree/>
          <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="POST /discovery/incoming-likes" enabled="true">
            <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
            <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="Body" enabled="true">
              <collectionProp name="Arguments.arguments">
                <elementProp name="" elementType="HTTPArgument">
                  <boolProp name="HTTPArgument.always_encode">false</boolProp>
                  <stringProp name="Argument.value">{"telegram_id":${telegram_id},"mode":"inbox","limit":10}</stringProp>
                  <stringProp name="Argument.metadata">=</stringProp>
                </elementProp>
              </collectionProp>
            </elementProp>
            <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
            <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
            <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
            <stringProp name="HTTPSampler.path">/discovery/incoming-likes</stringProp>
            <stringProp name="HTTPSampler.method">POST</stringProp>
            <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
            <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          </HTTPSamplerProxy>
          <hashTree>
            <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="inbox 200" enabled="true">
              <collectionProp name="Asserion.test_strings">
                <stringProp name="0">200</stringProp>
              </collectionProp>
              <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
              <boolProp name="Assertion.assume_success">false</boolProp>
              <intProp name="Assertion.test_type">8</intProp>
            </ResponseAssertion>
            <hashTree/>
          </hashTree>
          <UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="think before next" enabled="true">
            <stringProp name="ConstantTimer.delay">${__P(think.ms.min,20)}</stringProp>
            <stringProp name="RandomTimer.range">${__P(think.ms.range,180)}</stringProp>
          </UniformRandomTimer>
          <hashTree/>
          <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="POST /discovery/next" enabled="true">
            <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
            <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="Body" enabled="true">
              <collectionProp name="Arguments.arguments">
                <elementProp name="" elementType="HTTPArgument">
                  <boolProp name="HTTPArgument.always_encode">false</boolProp>
                  <stringProp name="Argument.value">{"telegram_id":${telegram_id}}</stringProp>
                  <stringProp name="Argument.metadata">=</stringProp>
                </elementProp>
              </collectionProp>
            </elementProp>
            <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
            <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
            <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
            <stringProp name="HTTPSampler.path">/discovery/next</stringProp>
            <stringProp name="HTTPSampler.method">POST</stringProp>
            <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
            <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
          </HTTPSamplerProxy>
          <hashTree>
            <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="next 200" enabled="true">
              <collectionProp name="Asserion.test_strings">
                <stringProp name="0">200</stringProp>
              </collectionProp>
              <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
              <boolProp name="Assertion.assume_success">false</boolProp>
              <intProp name="Assertion.test_type">8</intProp>
            </ResponseAssertion>
            <hashTree/>
            <RegexExtractor guiclass="RegexExtractorGui" testclass="RegexExtractor" testname="target_user_id" enabled="true">
              <stringProp name="RegexExtractor.useHeaders">false</stringProp>
              <stringProp name="RegexExtractor.refname">target_user_id</stringProp>
              <stringProp name="RegexExtractor.regex">"target_user_id"\s*:\s*"([a-fA-F0-9-]{36})"</stringProp>
              <stringProp name="RegexExtractor.template">$1$</stringProp>
              <stringProp name="RegexExtractor.default"></stringProp>
              <stringProp name="RegexExtractor.match_number">1</stringProp>
            </RegexExtractor>
            <hashTree/>
            <JSR223PostProcessor guiclass="TestBeanGUI" testclass="JSR223PostProcessor" testname="choose like vs skip" enabled="true">
              <stringProp name="cacheKey">true</stringProp>
              <stringProp name="filename"></stringProp>
              <stringProp name="parameters"></stringProp>
              <stringProp name="script"><![CDATA[
import org.apache.jmeter.util.JMeterUtils
def t = vars.get("target_user_id")
if (t == null || t.trim().isEmpty()) {
  vars.put("has_target", "0")
  vars.put("do_like", "0")
} else {
  vars.put("has_target", "1")
  double p = Double.parseDouble(JMeterUtils.getPropDefault("likeRatio", "0.22"))
  vars.put("do_like", java.util.concurrent.ThreadLocalRandom.current().nextDouble() < p ? "1" : "0")
}
]]></stringProp>
              <stringProp name="scriptLanguage">groovy</stringProp>
            </JSR223PostProcessor>
            <hashTree/>
          </hashTree>
          <UniformRandomTimer guiclass="UniformRandomTimerGui" testclass="UniformRandomTimer" testname="think before action" enabled="true">
            <stringProp name="ConstantTimer.delay">${__P(think.action.min,25)}</stringProp>
            <stringProp name="RandomTimer.range">${__P(think.action.range,220)}</stringProp>
          </UniformRandomTimer>
          <hashTree/>
          <IfController guiclass="IfControllerPanel" testclass="IfController" testname="If has profile card" enabled="true">
            <stringProp name="IfController.condition">${__jexl3(vars.get("has_target") == "1",)}</stringProp>
            <boolProp name="IfController.evaluateAll">false</boolProp>
            <boolProp name="IfController.useExpression">true</boolProp>
          </IfController>
          <hashTree>
            <IfController guiclass="IfControllerPanel" testclass="IfController" testname="If like branch" enabled="true">
              <stringProp name="IfController.condition">${__jexl3(vars.get("do_like") == "1",)}</stringProp>
              <boolProp name="IfController.evaluateAll">false</boolProp>
              <boolProp name="IfController.useExpression">true</boolProp>
            </IfController>
            <hashTree>
              <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="POST /discovery/like" enabled="true">
                <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
                <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="Body" enabled="true">
                  <collectionProp name="Arguments.arguments">
                    <elementProp name="" elementType="HTTPArgument">
                      <boolProp name="HTTPArgument.always_encode">false</boolProp>
                      <stringProp name="Argument.value">{"telegram_id":${telegram_id},"target_user_id":"${target_user_id}"}</stringProp>
                      <stringProp name="Argument.metadata">=</stringProp>
                    </elementProp>
                  </collectionProp>
                </elementProp>
                <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
                <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
                <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
                <stringProp name="HTTPSampler.path">/discovery/like</stringProp>
                <stringProp name="HTTPSampler.method">POST</stringProp>
                <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
                <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
              </HTTPSamplerProxy>
              <hashTree>
                <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="like 200 or 409" enabled="true">
                  <collectionProp name="Asserion.test_strings">
                    <stringProp name="0">^(200|409)$</stringProp>
                  </collectionProp>
                  <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
                  <boolProp name="Assertion.assume_success">false</boolProp>
                  <intProp name="Assertion.test_type">2</intProp>
                </ResponseAssertion>
                <hashTree/>
              </hashTree>
            </hashTree>
            <IfController guiclass="IfControllerPanel" testclass="IfController" testname="If skip branch" enabled="true">
              <stringProp name="IfController.condition">${__jexl3(vars.get("do_like") == "0",)}</stringProp>
              <boolProp name="IfController.evaluateAll">false</boolProp>
              <boolProp name="IfController.useExpression">true</boolProp>
            </IfController>
            <hashTree>
              <HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="POST /discovery/skip" enabled="true">
                <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
                <elementProp name="HTTPsampler.Arguments" elementType="Arguments" guiclass="HTTPArgumentsPanel" testclass="Arguments" testname="Body" enabled="true">
                  <collectionProp name="Arguments.arguments">
                    <elementProp name="" elementType="HTTPArgument">
                      <boolProp name="HTTPArgument.always_encode">false</boolProp>
                      <stringProp name="Argument.value">{"telegram_id":${telegram_id},"target_user_id":"${target_user_id}"}</stringProp>
                      <stringProp name="Argument.metadata">=</stringProp>
                    </elementProp>
                  </collectionProp>
                </elementProp>
                <stringProp name="HTTPSampler.domain">${__P(api.host,localhost)}</stringProp>
                <stringProp name="HTTPSampler.port">${__P(api.port,8000)}</stringProp>
                <stringProp name="HTTPSampler.protocol">${__P(api.protocol,http)}</stringProp>
                <stringProp name="HTTPSampler.path">/discovery/skip</stringProp>
                <stringProp name="HTTPSampler.method">POST</stringProp>
                <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
                <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
              </HTTPSamplerProxy>
              <hashTree>
                <ResponseAssertion guiclass="AssertionGui" testclass="ResponseAssertion" testname="skip 200 or 409" enabled="true">
                  <collectionProp name="Asserion.test_strings">
                    <stringProp name="0">^(200|409)$</stringProp>
                  </collectionProp>
                  <stringProp name="Assertion.test_field">Assertion.response_code</stringProp>
                  <boolProp name="Assertion.assume_success">false</boolProp>
                  <intProp name="Assertion.test_type">2</intProp>
                </ResponseAssertion>
                <hashTree/>
              </hashTree>
            </hashTree>
          </hashTree>
        </hashTree>
      </hashTree>
    </hashTree>
  </hashTree>
</jmeterTestPlan>
'''


def main() -> None:
    OUT.write_text(JMX, encoding="utf-8")
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
