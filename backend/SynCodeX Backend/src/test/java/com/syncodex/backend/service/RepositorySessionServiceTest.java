package com.syncodex.backend.service;

import com.syncodex.backend.dto.RepositoryContext;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.mock.web.MockHttpSession;

import java.nio.file.Files;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class RepositorySessionServiceTest {
    @TempDir Path temporaryDirectory;

    @Test
    void selectedRepositoriesAreIsolatedByHttpSessionAndCanBeSwitched() throws Exception {
        Path first = Files.createDirectory(temporaryDirectory.resolve("first"));
        Path second = Files.createDirectory(temporaryDirectory.resolve("second"));
        Path third = Files.createDirectory(temporaryDirectory.resolve("third"));
        RepositorySessionService service = new RepositorySessionService(first.toString());
        MockHttpSession sessionA = new MockHttpSession();
        MockHttpSession sessionB = new MockHttpSession();

        RepositoryContext contextA = service.select(sessionA, first.toString());
        RepositoryContext contextB = service.select(sessionB, second.toString());
        assertEquals(first.toRealPath().toString(), contextA.root());
        assertEquals(second.toRealPath().toString(), contextB.root());
        assertNotEquals(contextA.sessionId(), contextB.sessionId());

        RepositoryContext switched = service.select(sessionA, third.toString());
        assertEquals(third.toRealPath().toString(), switched.root());
        assertEquals(second.toRealPath().toString(), service.current(sessionB).root());
    }

    @Test
    void selectedRepositoryMustExistAndBeADirectory() throws Exception {
        Path validDefault = Files.createDirectory(temporaryDirectory.resolve("default"));
        RepositorySessionService service = new RepositorySessionService(validDefault.toString());
        MockHttpSession session = new MockHttpSession();

        assertThrows(org.springframework.web.server.ResponseStatusException.class,
                () -> service.select(session, temporaryDirectory.resolve("missing").toString()));
        assertEquals(validDefault.toRealPath().toString(), service.current(session).root());
    }
}
