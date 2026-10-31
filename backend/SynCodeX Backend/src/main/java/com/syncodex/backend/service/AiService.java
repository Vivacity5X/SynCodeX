
package com.syncodex.backend.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.JsonNode;
import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import com.syncodex.backend.dto.RepositoryAnswer;
import com.syncodex.backend.dto.RepositoryContext;
import com.syncodex.backend.dto.RepositoryQuestionRequest;
import com.syncodex.backend.dto.DebugRequest;
import com.syncodex.backend.dto.FixProposalRequest;
import com.syncodex.backend.dto.PatchApprovalRequest;
import com.syncodex.backend.dto.PatchRevertRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpRequestFactory;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

import com.syncodex.backend.dto.McpRepositoryAnswer;
import java.nio.charset.StandardCharsets;
import java.io.IOException;
import java.util.Map;
import java.util.LinkedHashMap;

@Service
public class AiService {

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    @Autowired
    public AiService(
            RestClient.Builder builder,
            ObjectMapper objectMapper,
            @Value("${syncodex.ai-service.url}") String aiServiceUrl,
            @Value("${syncodex.ai-service.force-http1:true}") boolean forceHttp1
    ) {
        this(builder, objectMapper, aiServiceUrl,
                forceHttp1 ? new SimpleClientHttpRequestFactory() : null);
    }

    AiService(RestClient.Builder builder, ObjectMapper objectMapper, String aiServiceUrl) {
        this(builder, objectMapper, aiServiceUrl, null);
    }

    private AiService(
            RestClient.Builder builder,
            ObjectMapper objectMapper,
            String aiServiceUrl,
            ClientHttpRequestFactory requestFactory
    ) {
        if (requestFactory != null) {
            builder.requestFactory(requestFactory);
        }
        this.restClient = builder
                .baseUrl(aiServiceUrl)
                .build();

        this.objectMapper = objectMapper;
    }

    public ExplainResponse explainCode(ExplainRequest request) {
        if (request.code() == null || request.code().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Code cannot be empty"
            );
        }

        String language = request.language() == null
                || request.language().isBlank()
                ? "Java"
                : request.language();

        try {
            Map<?, ?> response = restClient.post()
                    .uri("/api/v1/explain")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of(
                            "code", request.code(),
                            "language", language
                    ))
                    .retrieve()
                    .body(Map.class);

            if (response == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "AI service returned an empty response"
                );
            }

            return new ExplainResponse(
                    String.valueOf(response.get("application") != null
                            ? response.get("application") : "SynCodeX"),
                    String.valueOf(response.get("language") != null
                            ? response.get("language") : language),
                    String.valueOf(response.get("explanation") != null
                            ? response.get("explanation") : ""),
                    String.valueOf(response.get("status") != null
                            ? response.get("status") : "success")
            );

        } catch (RestClientException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "AI service request failed"
            );
        }
    }



public RepositoryAnswer askRepository(RepositoryQuestionRequest request) {
    return askRepository(request, null);
}

public RepositoryAnswer askRepository(RepositoryQuestionRequest request, RepositoryContext context) {
    if (request.question() == null || request.question().isBlank()) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Question cannot be empty"
        );
    }

    try {
        byte[] jsonBody = objectMapper.writeValueAsBytes(
                withRepositoryContext(Map.of("question", request.question()), context)
        );

        byte[] responseBytes = restClient.post()
                .uri("/api/v1/repository/ask")
                .contentType(MediaType.APPLICATION_JSON)
                .body(jsonBody)
                .retrieve()
                .body(byte[].class);

        if (responseBytes == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "AI service returned an empty response"
            );
        }

        String responseBody = new String(responseBytes, StandardCharsets.UTF_8);
        return objectMapper.readValue(
                responseBody,
                RepositoryAnswer.class
        );

    } catch (JsonProcessingException ex) {
        throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not serialize or process the repository answer",
                ex
        );

    } catch (RestClientException ex) {
        System.err.println("AI service request failed:");
        ex.printStackTrace();

        throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "AI service request failed: " + ex.getMessage()
        );
    }
}


public McpRepositoryAnswer askRepositoryWithMcp(RepositoryQuestionRequest request) {
    return askRepositoryWithMcp(request, null);
}

public McpRepositoryAnswer askRepositoryWithMcp(RepositoryQuestionRequest request, RepositoryContext context) {
    if (request.question() == null || request.question().isBlank()) {
        throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Question cannot be empty"
        );
    }

    try {
        byte[] jsonBody = objectMapper.writeValueAsBytes(
                withRepositoryContext(Map.of("question", request.question()), context)
        );

        byte[] responseBytes = restClient.post()
                .uri("/api/v1/mcp/ask")
                .contentType(MediaType.APPLICATION_JSON)
                .body(jsonBody)
                .retrieve()
                .body(byte[].class);

        if (responseBytes == null) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "AI service returned an empty MCP response"
            );
        }

        String responseBody = new String(responseBytes, StandardCharsets.UTF_8);
        return objectMapper.readValue(
                responseBody,
                McpRepositoryAnswer.class
        );

    } catch (JsonProcessingException ex) {
        throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "Could not process the MCP repository answer",
                ex
        );

    } catch (RestClientException ex) {
        throw new ResponseStatusException(
                HttpStatus.BAD_GATEWAY,
                "MCP repository request failed: " + ex.getMessage()
        );
    }
}

public Map<String, Object> analyzeDebug(DebugRequest request) {
    return analyzeDebug(request, null);
}

public Map<String, Object> analyzeDebug(DebugRequest request, RepositoryContext context) {
    String error = valueOrEmpty(request.error());
    String question = valueOrEmpty(request.question());
    String logs = valueOrEmpty(request.logs());
    String projectContext = valueOrEmpty(request.projectContext());
    if (error.isBlank() && logs.isBlank()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Provide an error or logs");
    }
    if (error.length() > 12_000 || logs.length() > 12_000
            || question.length() > 2_000 || projectContext.length() > 4_000) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Debug request exceeds the supported size limit");
    }
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("error", error);
    payload.put("question", question);
    payload.put("logs", logs);
    payload.put("project_context", projectContext);
    payload = withRepositoryContext(payload, context);
    return postAiServiceMap("/api/v1/debug/analyze", payload, "Debug analysis request failed");
}

public Map<String, Object> proposeFix(FixProposalRequest request) {
    return proposeFix(request, null);
}

public Map<String, Object> proposeFix(FixProposalRequest request, RepositoryContext context) {
    String file = valueOrEmpty(request.file());
    String instructions = valueOrEmpty(request.instructions());
    String error = valueOrEmpty(request.error());
    String question = valueOrEmpty(request.question());
    if (file.isBlank() || instructions.isBlank()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "A file and change instructions are required");
    }
    if (file.length() > 400 || instructions.length() > 2_000
            || error.length() > 12_000 || question.length() > 2_000) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Patch request exceeds the supported size limit");
    }
    Map<String, Object> payload = new LinkedHashMap<>();
    payload.put("file", file);
    payload.put("instructions", instructions);
    payload.put("error", error);
    payload.put("question", question);
    payload = withRepositoryContext(payload, context);
    return postAiServiceMap("/api/v1/debug/propose-fix", payload, "Patch proposal request failed");
}

public Map<String, Object> applyFix(PatchApprovalRequest request) {
    return applyFix(request, null);
}

public Map<String, Object> applyFix(PatchApprovalRequest request, RepositoryContext context) {
    if (request.proposalId() == null || request.proposalId().length() != 32 || !request.approved()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "An explicit approval and valid proposal ID are required");
    }
    return postAiServiceMap("/api/v1/debug/apply-fix", withRepositoryContext(new LinkedHashMap<>(Map.of(
            "proposal_id", request.proposalId(),
            "approved", true
    )), context), "Patch application request failed");
}

public Map<String, Object> revertFix(PatchRevertRequest request) {
    return revertFix(request, null);
}

public Map<String, Object> revertFix(PatchRevertRequest request, RepositoryContext context) {
    if (request.backupId() == null || request.backupId().length() != 32
            || request.file() == null || request.file().isBlank()
            || request.expectedCurrentSha256() == null || request.expectedCurrentSha256().length() != 64
            || !request.approved()) {
        throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Explicit approval and valid revert details are required");
    }
    return postAiServiceMap("/api/v1/debug/revert-fix", withRepositoryContext(new LinkedHashMap<>(Map.of(
            "backup_id", request.backupId(),
            "file", request.file(),
            "expected_current_sha256", request.expectedCurrentSha256(),
            "approved", true
    )), context), "Patch revert request failed");
}

public Map<String, Object> inspectRepository(RepositoryContext context) {
    return postAiServiceMap("/api/v1/repository/inspect", withRepositoryContext(new LinkedHashMap<>(), context),
            "Repository inspection request failed");
}

private Map<String, Object> withRepositoryContext(Map<String, Object> payload, RepositoryContext context) {
    Map<String, Object> contextualPayload = new LinkedHashMap<>(payload);
    if (context != null) {
        contextualPayload.put("repository_root", context.root());
        contextualPayload.put("session_id", context.sessionId());
    }
    return contextualPayload;
}

private Map<String, Object> postAiServiceMap(
        String path,
        Map<String, Object> payload,
        String failureMessage
) {
    try {
        byte[] jsonBody = objectMapper.writeValueAsBytes(payload);
        Map<?, ?> response = restClient.post()
                .uri(path)
                .contentType(MediaType.APPLICATION_JSON)
                .body(jsonBody)
                .retrieve()
                .body(Map.class);
        if (response == null) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "AI service returned an empty response");
        }
        Map<String, Object> result = new LinkedHashMap<>();
        response.forEach((key, value) -> result.put(String.valueOf(key), value));
        return result;
    } catch (JsonProcessingException ex) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, "Could not serialize the AI service request");
    } catch (RestClientResponseException ex) {
        HttpStatusCode status = ex.getStatusCode();
        throw new ResponseStatusException(status, downstreamDetail(ex));
    } catch (RestClientException ex) {
        throw new ResponseStatusException(HttpStatus.BAD_GATEWAY, failureMessage);
    }
}

private String downstreamDetail(RestClientResponseException exception) {
    try {
        JsonNode body = objectMapper.readTree(exception.getResponseBodyAsByteArray());
        JsonNode detail = body == null ? null : body.get("detail");
        if (detail != null && detail.isTextual() && !detail.asText().isBlank()) {
            return detail.asText();
        }
        if (detail != null && detail.isArray()) {
            StringBuilder message = new StringBuilder("AI service request validation failed: ");
            for (JsonNode error : detail) {
                if (message.length() > 50) message.append("; ");
                JsonNode location = error.path("loc");
                String field = location.isArray() && location.size() > 1
                        ? location.get(location.size() - 1).asText()
                        : "request";
                String reason = error.path("msg").asText("invalid value");
                message.append(field).append(": ").append(reason);
            }
            if (message.length() > 50) return message.toString();
        }
    } catch (IOException ignored) {
        // Fall back to the status-based message when the downstream body is not JSON.
    }
    return "AI service rejected the request (HTTP " + exception.getStatusCode().value() + ").";
}

private String valueOrEmpty(String value) {
    return value == null ? "" : value;
}


}
