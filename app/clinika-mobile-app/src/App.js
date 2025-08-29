import React, { useState, useRef, useEffect } from 'react';

// Define la URL base de tu servidor Flask, que será la URL de LocalTunnel.
// ¡IMPORTANTE!: Reemplaza 'https://your-localtunnel-url.loca.lt' con la URL real
// que LocalTunnel te proporcione en la terminal cuando lo inicies (ej. https://small-toys-brake.loca.lt).
const API_BASE_URL = 'https://dionnem.pythonanywhere.com'; // **MODIFICA ESTA LÍNEA CON TU URL ACTUAL DE LOCAL TUNNEL**

// Main App component
const App = () => {
    // Estado para gestionar los mensajes del chat
    const [chatHistory, setChatHistory] = useState([
        { sender: 'ai', message: 'Hola, soy tu Asistente Médico Virtual. ¿En qué puedo ayudarte hoy?' },
    ]);
    // Estado para el mensaje actual que el usuario está escribiendo
    const [currentMessage, setCurrentMessage] = useState('');
    // Estado para mostrar mensajes de estado (ej. estado de carga de archivos)
    const [statusMessage, setStatusMessage] = useState('');
    // Referencia para el elemento de entrada de archivo oculto
    const fileInputRef = useRef(null);
    // Referencia para el div del historial del chat para permitir el desplazamiento
    const chatHistoryRef = useRef(null);
    // Estado para el indicador de carga en el chat
    const [isLoading, setIsLoading] = useState(false);
    // NUEVO: Estado para almacenar el ID del paciente actual en discusión
    const [currentPatientId, setCurrentPatientId] = useState(null);
    // Estado para la última respuesta de la IA (para exportar a PDF)
    const [lastAiResponse, setLastAiResponse] = useState('');

    // Efecto para desplazarse automáticamente al final del historial del chat
    useEffect(() => {
        if (chatHistoryRef.current) {
            chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
        }
    }, [chatHistory]);

    // Función para añadir un mensaje al historial del chat
    const addChatMessage = (message, sender) => {
        setChatHistory((prevHistory) => {
            const newHistory = [...prevHistory, { sender, message }];
            // Actualizar la última respuesta de la IA si el remitente es la IA
            if (sender === 'ai') {
                setLastAiResponse(message);
            }
            return newHistory;
        });
    };

    // Manejador para el clic en el botón de documento
    const handleDocumentClick = () => {
        fileInputRef.current.click();
    };

    // Manejador para el cambio de archivo (cuando se selecciona un archivo)
    const handleFileChange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        setIsLoading(true);
        setStatusMessage('Cargando documento...');
        addChatMessage(`Cargando documento: ${file.name}...`, 'user');

        const formData = new FormData();
        formData.append('document', file);

        try {
            const response = await fetch(`${API_BASE_URL}/procesar`, {
                method: 'POST',
                body: formData,
            });

            const data = await response.json();

            if (response.ok) {
                setStatusMessage(data.mensaje);
                addChatMessage(`📄 ${data.mensaje}`, 'ai');
                addChatMessage(`📊 Análisis automático del documento:\n\n${data.analisis_nlp}`, 'ai');
                // NUEVO: Establecer el ID del paciente actual desde la respuesta del backend
                if (data.patient_id) {
                    setCurrentPatientId(data.patient_id);
                    addChatMessage(`Contexto establecido para el Paciente ID: ${data.patient_id}`, 'ai');
                } else {
                    setCurrentPatientId(null); // Limpiar si no se devuelve ID
                }
            } else {
                const errorText = data.mensaje || 'Error desconocido';
                setStatusMessage(`Error al procesar: ${errorText}`);
                addChatMessage(`Error al procesar documento "${file.name}": ${errorText}`, 'ai');
                setCurrentPatientId(null); // Limpiar contexto en caso de error
            }
        } catch (error) {
            console.error('Error al subir el documento:', error);
            setStatusMessage(`Error de red al subir el documento: ${error.message}`);
            addChatMessage(`Error de red al subir el documento: ${error.message}`, 'ai');
            setCurrentPatientId(null); // Limpiar contexto en caso de error
        } finally {
            setIsLoading(false);
        }
    };

    // Manejador para enviar un mensaje de chat
    const handleSendMessage = async () => {
        const messageToSend = currentMessage.trim();
        if (!messageToSend) return;

        addChatMessage(messageToSend, 'user');
        setCurrentMessage('');
        setIsLoading(true);
        setStatusMessage('Generando respuesta...');

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    message: messageToSend,
                    // Enviar el historial completo del chat para el contexto
                    chat_history: chatHistory.map(msg => ({
                        sender: msg.sender, // 'user' o 'ai'
                        message: msg.message
                    })),
                    // NUEVO: Enviar el ID del paciente activo
                    current_patient_id: currentPatientId,
                }),
            });

            const data = await response.json();

            if (response.ok) {
                addChatMessage(data.response, 'ai');
                setStatusMessage('Respuesta generada.');
            } else {
                const errorText = data.error || 'Error desconocido';
                setStatusMessage(`Error al generar respuesta: ${errorText}`);
                addChatMessage(`Error: ${errorText}`, 'ai');
            }
        } catch (error) {
            console.error('Error al enviar mensaje:', error);
            setStatusMessage(`Error de red: ${error.message}`);
            addChatMessage(`Error de red: ${error.message}`, 'ai');
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-screen bg-gray-900 text-gray-100 font-inter">
            {/* Header */}
            <header className="p-4 bg-gray-800 border-b border-gray-700 flex items-center justify-between">
                <h1 className="text-2xl font-bold text-blue-400">Asistente Médico Virtual</h1>
                <div className="flex items-center space-x-2">
                    {currentPatientId && ( // Mostrar el ID del paciente si está activo
                        <span className="text-sm text-gray-400 px-3 py-1 bg-gray-700 rounded-full">
                            Paciente: {currentPatientId}
                        </span>
                    )}
                    <button className="p-2 rounded-full bg-gray-700 hover:bg-gray-600 transition-colors duration-200">
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6 text-gray-300">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z" />
                        </svg>
                    </button>
                </div>
            </header>

            {/* Main Chat Area */}
            <main className="flex-1 overflow-hidden p-4 flex flex-col">
                <div ref={chatHistoryRef} className="flex-1 overflow-y-auto pr-4 mb-4 custom-scrollbar">
                    {chatHistory.map((chat, index) => (
                        <div
                            key={index}
                            className={`flex mb-3 ${chat.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            <div
                                className={`max-w-[70%] p-3 rounded-lg shadow-md ${
                                    chat.sender === 'user'
                                        ? 'bg-blue-600 text-white rounded-br-none'
                                        : 'bg-gray-700 text-gray-100 rounded-bl-none'
                                }`}
                            >
                                {chat.message}
                            </div>
                        </div>
                    ))}
                    {isLoading && (
                        <div className="flex justify-start mb-3">
                            <div className="max-w-[70%] p-3 rounded-lg shadow-md bg-gray-700 text-gray-100 rounded-bl-none loading-bubble">
                                <span>•</span><span>•</span><span>•</span>
                            </div>
                        </div>
                    )}
                </div>

                {statusMessage && (
                    <div className="text-center text-sm text-gray-400 mb-2">
                        {statusMessage}
                    </div>
                )}
            </main>

            {/* Footer - Input and Buttons */}
            <footer className="p-4 bg-gray-800 border-t border-gray-700">
                <div className="flex items-center space-x-3 mb-4">
                    <input
                        type="text"
                        value={currentMessage}
                        onChange={(e) => setCurrentMessage(e.target.value)}
                        onKeyPress={(e) => {
                            if (e.key === 'Enter') {
                                handleSendMessage();
                            }
                        }}
                        placeholder={isLoading ? "Espera un momento..." : "Escribe tu mensaje..."}
                        className="flex-1 p-3 rounded-full bg-gray-700 text-gray-100 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-blue-500 border border-gray-600"
                        disabled={isLoading}
                    />
                    <button
                        onClick={handleSendMessage}
                        className="p-3 bg-blue-600 text-white rounded-full shadow-lg hover:bg-blue-700 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
                        disabled={isLoading}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5" />
                        </svg>
                    </button>
                    {/* Botón de exportar a PDF */}
                    <button
                        onClick={async () => {
                            addChatMessage("Generando PDF de la última respuesta de la IA...", "ai");
                            try {
                                const response = await fetch(`${API_BASE_URL}/export_chat_response_pdf`, {
                                    method: 'POST',
                                    headers: {
                                        'Content-Type': 'application/json'
                                    },
                                    body: JSON.stringify({ text_content: lastAiResponse })
                                });

                                if (response.ok) {
                                    const blob = await response.blob();
                                    const url = window.URL.createObjectURL(blob);
                                    const a = document.createElement('a');
                                    a.href = url;
                                    a.download = 'respuesta_chatbot.pdf';
                                    document.body.appendChild(a);
                                    a.click();
                                    a.remove();
                                    window.URL.revokeObjectURL(url);
                                    addChatMessage("PDF de la respuesta del chatbot generado y descargado.", "ai");
                                } else {
                                    const errorText = await response.text();
                                    addChatMessage(`Error al generar el PDF de la respuesta del chatbot: ${errorText}`, "ai");
                                }
                            } catch (error) {
                                addChatMessage(`Error de red al generar el PDF: ${error.message}`, "ai");
                                console.error('Error al exportar chat a PDF:', error);
                            }
                        }}
                        className="p-3 bg-green-600 text-white rounded-full shadow-lg hover:bg-green-700 transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-green-500"
                        title="Exportar última respuesta a PDF"
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="1.5" stroke="currentColor" className="w-6 h-6">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m.75 12l3 3m0 0l3-3m-3 3V2.25" />
                        </svg>
                    </button>
                </div>

                {/* Attachment Buttons */}
                <div className="flex justify-around space-x-2 text-sm">
                    <button className="flex items-center px-4 py-2 bg-gray-700 text-gray-300 rounded-full hover:bg-gray-600 transition-colors duration-200">
                        <span className="text-xl mr-2">📸</span> Foto
                    </button>
                    <button
                        onClick={handleDocumentClick}
                        className="flex items-center px-4 py-2 bg-gray-700 text-gray-300 rounded-full hover:bg-gray-600 transition-colors duration-200"
                        disabled={isLoading}
                    >
                        <span className="text-xl mr-2">📄</span> Documento...
                    </button>
                    <input
                        type="file"
                        ref={fileInputRef}
                        onChange={handleFileChange}
                        className="hidden"
                        accept=".pdf,.txt"
                    />
                    <button className="flex items-center px-4 py-2 bg-gray-700 text-gray-300 rounded-full hover:bg-gray-600 transition-colors duration-200">
                        <span className="text-xl mr-2">🔗</span> Enlace...
                    </button>
                </div>
            </footer>
        </div>
    );
};

export default App;