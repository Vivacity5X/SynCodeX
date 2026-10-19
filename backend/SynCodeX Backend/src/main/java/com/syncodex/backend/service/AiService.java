
package com.syncodex.backend.service;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import com.syncodex.backend.dto.RepositoryAnswer;
import com.syncodex.backend.dto.RepositoryQuestionRequest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientException;
import org.springframework.web.server.ResponseStatusException;

import java.util.Map;

@Service
public class AiService {

    private final RestClient restClient;
    private final ObjectMapper objectMapper;

    public AiService(
            RestClient.Builder builder,
            ObjectMapper objectMapper,
            @Value("${syncodex.ai-service.url}") String aiServiceUrl
    ) {
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
        if (request.question() == null || request.question().isBlank()) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "Question cannot be empty"
            );
        }

        try {
            String responseBody = restClient.post()
                    .uri("/api/v1/repository/ask")
                    .contentType(MediaType.APPLICATION_JSON)
                    .body(Map.of("question", request.question()))
                    .retrieve()
                    .body(String.class);

            if (responseBody == null) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_GATEWAY,
                        "AI service returned an empty response"
                );
            }

            return objectMapper.readValue(
                    responseBody,
                    RepositoryAnswer.class
            );

        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "Could not process the repository answer"
            );

        } catch (RestClientException ex) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_GATEWAY,
                    "AI service request failed"
            );
        }
    }

}
