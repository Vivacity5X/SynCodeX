package com.syncodex.backend.service;

import com.syncodex.backend.dto.RepositoryContext;
import jakarta.servlet.http.HttpSession;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

@Service
public class RepositorySessionService {
    private static final String ROOT_ATTRIBUTE = "syncodex.repository.root";
    private final Path defaultRoot;

    public RepositorySessionService(@Value("${syncodex.repository.default-root:}") String configuredRoot) {
        this.defaultRoot = configuredRoot == null || configuredRoot.isBlank()
                ? discoverDefaultRoot()
                : validate(configuredRoot);
    }

    public RepositoryContext current(HttpSession session) {
        Object existing = session.getAttribute(ROOT_ATTRIBUTE);
        Path root = existing instanceof String value ? validate(value) : defaultRoot;
        session.setAttribute(ROOT_ATTRIBUTE, root.toString());
        return new RepositoryContext(root.toString(), session.getId());
    }

    public RepositoryContext select(HttpSession session, String requestedPath) {
        RepositoryContext context = validateSelection(session, requestedPath);
        activate(session, context);
        return context;
    }

    public RepositoryContext validateSelection(HttpSession session, String requestedPath) {
        Path root = validate(requestedPath);
        return new RepositoryContext(root.toString(), session.getId());
    }

    public void activate(HttpSession session, RepositoryContext context) {
        if (!session.getId().equals(context.sessionId())) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "Repository selection belongs to a different browser session.");
        }
        session.setAttribute(ROOT_ATTRIBUTE, validate(context.root()).toString());
    }

    private Path validate(String value) {
        if (value == null || value.isBlank() || value.length() > 2_000) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Choose an existing local project directory.");
        }
        try {
            Path root = Path.of(value.trim()).toRealPath();
            if (!Files.isDirectory(root) || root.getParent() == null) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The selected path must be a project directory, not a filesystem root.");
            }
            return root;
        } catch (IOException | RuntimeException exception) {
            if (exception instanceof ResponseStatusException responseStatusException) {
                throw responseStatusException;
            }
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "The selected repository directory is unavailable.");
        }
    }

    private Path discoverDefaultRoot() {
        Path current = Path.of("").toAbsolutePath().normalize();
        while (current != null) {
            if (Files.isDirectory(current.resolve("ai-service"))
                    && Files.isDirectory(current.resolve("mcp-server"))) {
                return validate(current.toString());
            }
            current = current.getParent();
        }
        return validate(Path.of("").toAbsolutePath().normalize().toString());
    }
}
