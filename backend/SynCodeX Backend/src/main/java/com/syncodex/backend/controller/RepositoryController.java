package com.syncodex.backend.controller;

import com.syncodex.backend.dto.RepositoryContext;
import com.syncodex.backend.dto.RepositorySelectionRequest;
import com.syncodex.backend.service.AiService;
import com.syncodex.backend.service.RepositorySessionService;
import jakarta.servlet.http.HttpSession;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.util.WebUtils;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.util.LinkedHashMap;
import java.util.Map;

@RestController
@RequestMapping("/api/v1/ai/repository")
public class RepositoryController {
    private final RepositorySessionService repositorySessions;
    private final AiService aiService;

    public RepositoryController(RepositorySessionService repositorySessions, AiService aiService) {
        this.repositorySessions = repositorySessions;
        this.aiService = aiService;
    }

    @GetMapping("/context")
    public Map<String, Object> current(HttpSession session) {
        synchronized (WebUtils.getSessionMutex(session)) {
            return inspect(repositorySessions.current(session));
        }
    }

    @PostMapping("/select")
    public Map<String, Object> select(@RequestBody RepositorySelectionRequest request, HttpSession session) {
        if (request == null || request.path() == null || request.path().isBlank()) {
            throw new ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST,
                    "Provide a local repository directory path.");
        }
        if (request.path().length() > 2_000) {
            throw new ResponseStatusException(org.springframework.http.HttpStatus.BAD_REQUEST,
                    "The repository path is too long.");
        }
        synchronized (WebUtils.getSessionMutex(session)) {
            RepositoryContext candidate = repositorySessions.validateSelection(session, request.path());
            Map<String, Object> profile = inspect(candidate);
            repositorySessions.activate(session, candidate);
            return profile;
        }
    }

    private Map<String, Object> inspect(RepositoryContext context) {
        Map<String, Object> response = new LinkedHashMap<>(aiService.inspectRepository(context));
        response.put("repository", context.root());
        return response;
    }

    @org.springframework.web.bind.annotation.ExceptionHandler(ResponseStatusException.class)
    public ResponseEntity<Map<String, String>> handleSelectionFailure(ResponseStatusException exception) {
        String detail = exception.getReason() == null ? "Repository selection failed." : exception.getReason();
        return ResponseEntity.status(exception.getStatusCode()).body(Map.of("detail", detail));
    }

    @org.springframework.web.bind.annotation.ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> handleMalformedSelection(HttpMessageNotReadableException exception) {
        return ResponseEntity.badRequest().body(Map.of(
                "detail", "Request body must be JSON with a non-empty 'path' string."
        ));
    }
}
