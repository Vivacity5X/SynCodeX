package com.syncodex.backend.service;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.syncodex.backend.dto.ExplainRequest;
import com.syncodex.backend.dto.ExplainResponse;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.client.RestClient;
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
}
