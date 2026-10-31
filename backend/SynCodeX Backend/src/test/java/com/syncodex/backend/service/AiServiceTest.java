package com.syncodex.backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import com.syncodex.backend.dto.DebugRequest;
import com.syncodex.backend.dto.RepositoryContext;
import com.syncodex.backend.dto.RepositoryQuestionRequest;
import com.syncodex.backend.dto.FixProposalRequest;
import com.syncodex.backend.dto.PatchApprovalRequest;
import com.syncodex.backend.dto.PatchRevertRequest;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.test.web.client.match.MockRestRequestMatchers;
import org.springframework.test.web.client.response.MockRestResponseCreators;
import org.springframework.http.HttpMethod;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class AiServiceTest {

    @Test
    void shouldRejectEmptyCode() {
        AiService service = new AiService(
                RestClient.builder(),
                new ObjectMapper(),
                "http://127.0.0.1:8000"
        );

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.explainCode(
                        new ExplainRequest("   ", "Java")
                )
        );

        assertEquals(
                HttpStatus.BAD_REQUEST,
                exception.getStatusCode()
        );
    }

    @Test
    void shouldRejectDebugRequestWithoutErrorOrLogs() {
        AiService service = new AiService(
                RestClient.builder(),
                new ObjectMapper(),
                "http://127.0.0.1:8000"
        );

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.analyzeDebug(new DebugRequest("", "", "", ""))
        );

        assertEquals(HttpStatus.BAD_REQUEST, exception.getStatusCode());
    }

    @Test
    void shouldRejectOversizedPatchInstructions() {
        AiService service = new AiService(
                RestClient.builder(),
                new ObjectMapper(),
                "http://127.0.0.1:8000"
        );

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.proposeFix(new FixProposalRequest(
                        "src/Main.java",
                        "x".repeat(2_001),
                        "",
                        ""
                ))
        );

        assertEquals(HttpStatus.BAD_REQUEST, exception.getStatusCode());
    }

    @Test
    void shouldRequireExplicitPatchApproval() {
        AiService service = new AiService(
                RestClient.builder(),
                new ObjectMapper(),
                "http://127.0.0.1:8000"
        );

        ResponseStatusException exception = assertThrows(
                ResponseStatusException.class,
                () -> service.applyFix(new PatchApprovalRequest("0123456789abcdef0123456789abcdef", false))
        );

        assertEquals(HttpStatus.BAD_REQUEST, exception.getStatusCode());
    }

    @Test
    void shouldForwardDebugAndPatchContractsToAiService() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        AiService service = new AiService(builder, new ObjectMapper(), "http://127.0.0.1:8000");

        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/debug/analyze"))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.POST))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"error\":\"trace\",\"question\":\"why\",\"logs\":\"log\",\"project_context\":\"context\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"analysis_status\":\"provider_unconfigured\",\"evidence\":[]}",
                        MediaType.APPLICATION_JSON
                ));
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/debug/propose-fix"))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.POST))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"file\":\"src/Main.java\",\"instructions\":\"change\",\"error\":\"trace\",\"question\":\"why\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"proposal_id\":\"0123456789abcdef0123456789abcdef\",\"applied\":false}",
                        MediaType.APPLICATION_JSON
                ));
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/debug/apply-fix"))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"proposal_id\":\"0123456789abcdef0123456789abcdef\",\"approved\":true}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess("{\"applied\":true}", MediaType.APPLICATION_JSON));
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/debug/revert-fix"))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"backup_id\":\"0123456789abcdef0123456789abcdef\",\"file\":\"src/Main.java\",\"expected_current_sha256\":\"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\",\"approved\":true}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess("{\"reverted\":true}", MediaType.APPLICATION_JSON));
        Map<String, Object> report = service.analyzeDebug(new DebugRequest("trace", "why", "log", "context"));
        assertEquals("provider_unconfigured", report.get("analysis_status"));
        assertEquals(false, service.proposeFix(
                new FixProposalRequest("src/Main.java", "change", "trace", "why")
        ).get("applied"));
        assertEquals(true, service.applyFix(
                new PatchApprovalRequest("0123456789abcdef0123456789abcdef", true)
        ).get("applied"));
        assertEquals(true, service.revertFix(new PatchRevertRequest(
                "0123456789abcdef0123456789abcdef",
                "src/Main.java",
                "a".repeat(64),
                true
        )).get("reverted"));

        server.verify();
    }

    @Test
    void forwardsTheSelectedRepositoryAndSessionWithRepositoryRequests() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        AiService service = new AiService(builder, new ObjectMapper(), "http://127.0.0.1:8000");
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/repository/ask"))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"question\":\"how\",\"repository_root\":\"/samples/react-app\",\"session_id\":\"session-b\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"question\":\"how\",\"answer\":\"answer\",\"sources\":[],\"project\":{\"project_types\":[\"React/TypeScript\"]}}",
                        MediaType.APPLICATION_JSON
                ));
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/mcp/ask"))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"question\":\"how\",\"repository_root\":\"/samples/react-app\",\"session_id\":\"session-b\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"question\":\"how\",\"answer\":\"answer\",\"sources\":[],\"project\":{\"project_types\":[\"React/TypeScript\"]}}",
                        MediaType.APPLICATION_JSON
                ));
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/debug/analyze"))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"error\":\"trace\",\"question\":\"why\",\"logs\":\"\",\"project_context\":\"\",\"repository_root\":\"/samples/react-app\",\"session_id\":\"session-b\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"analysis_status\":\"provider_unconfigured\",\"evidence\":[]}",
                        MediaType.APPLICATION_JSON
                ));

        RepositoryContext context = new RepositoryContext("/samples/react-app", "session-b");
        assertEquals("answer", service.askRepository(new RepositoryQuestionRequest("how"), context).answer());
        assertEquals("answer", service.askRepositoryWithMcp(new RepositoryQuestionRequest("how"), context).answer());
        service.analyzeDebug(new DebugRequest("trace", "why", "", ""), context);
        server.verify();
    }

    @Test
    void inspectForwardsTheCanonicalWindowsPathAndSessionUsingTheFastApiSchema() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        AiService service = new AiService(builder, new ObjectMapper(), "http://127.0.0.1:8000");
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/repository/inspect"))
                .andExpect(MockRestRequestMatchers.method(HttpMethod.POST))
                .andExpect(MockRestRequestMatchers.content().json(
                        "{\"repository_root\":\"D:\\\\MCP-Test\\\\ProjectA\",\"session_id\":\"session-windows\"}"
                ))
                .andRespond(MockRestResponseCreators.withSuccess(
                        "{\"repository\":\"D:\\\\MCP-Test\\\\ProjectA\",\"project_types\":[],\"languages\":[\"Java\"],\"debug_languages\":[\"Java\"],\"unsupported_debug_languages\":[],\"message\":\"inspected\",\"manifests\":[]} ",
                        MediaType.APPLICATION_JSON
                ));

        Map<String, Object> result = service.inspectRepository(
                new RepositoryContext("D:\\MCP-Test\\ProjectA", "session-windows"));
        assertEquals("D:\\MCP-Test\\ProjectA", result.get("repository"));
        server.verify();
    }

    @Test
    void preservesFastApiValidationDetailForRepositorySelectionErrors() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer server = MockRestServiceServer.bindTo(builder).build();
        AiService service = new AiService(builder, new ObjectMapper(), "http://127.0.0.1:8000");
        server.expect(MockRestRequestMatchers.requestTo("http://127.0.0.1:8000/api/v1/repository/inspect"))
                .andRespond(MockRestResponseCreators.withStatus(HttpStatus.UNPROCESSABLE_ENTITY)
                        .contentType(MediaType.APPLICATION_JSON)
                        .body("{\"detail\":[{\"loc\":[\"body\",\"repository_root\"],\"msg\":\"Field required\",\"input\":null}]}"));

        ResponseStatusException exception = assertThrows(ResponseStatusException.class,
                () -> service.inspectRepository(new RepositoryContext("D:\\MCP-Test\\ProjectA", "session-a")));
        assertEquals(HttpStatus.UNPROCESSABLE_ENTITY, exception.getStatusCode());
        assertTrue(exception.getReason().contains("repository_root: Field required"));
        server.verify();
    }
}
