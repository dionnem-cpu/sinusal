import React, { useState, useRef } from 'react';
// import './index.css'; // Removed this line as it causes compilation error in this environment

// Define la URL base de tu servidor Flask, que será la URL de LocalTunnel.
// ¡IMPORTANTE!: Reemplaza 'https://your-localtunnel-url.loca.lt' con la URL real
// que LocalTunnel te proporcione en la terminal cuando lo inicies (ej. https://small-toys-brake.loca.lt).
const API_BASE_URL = 'https://brown-roses-flash.loca.lt'; // **MODIFICA ESTA LÍNEA CON TU URL ACTUAL DE LOCAL TUNNEL**

// Main App component
const App = () => {
    // State to manage chat messages
    const [chatHistory, setChatHistory] = useState([
        { sender: 'ai', message: 'Hola, soy tu Asistente Médico Virtual. ¿En qué puedo ayudarte hoy?' },
    ]);
    // State for the current message being typed by the user
    const [currentMessage, setCurrentMessage] = useState('');
    // State for displaying status messages (e.g., file upload status)
    const [statusMessage, setStatusMessage] = useState('');
    // Ref for the hidden file input element
    const fileInputRef = useRef(null);
    // Ref for the chat history div to enable scrolling
    const chatHistoryRef = useRef(null);
    // State for loading indicator in chat
    const [isLoading, setIsLoading] = useState(false);

    // Function to add a message to the chat history and scroll to the bottom
    const addChatMessage = (message, sender) => {
        setChatHistory((prevHistory) => {
            // Remove loading bubble if it exists before adding new message
            if (prevHistory.length > 0 && prevHistory[prevHistory.length - 1].sender === 'loading') {
                // Si el mensaje actual es de la IA, lo reemplazamos por el mensaje final de la IA.
                // Si el mensaje actual es de error, lo dejamos como un mensaje normal.
                const updatedHistory = prevHistory.slice(0, prevHistory.length - 1);
                return [...updatedHistory, { sender, message }];
            }
            return [...prevHistory, { sender, message }];
        });
        // Scroll to the bottom of the chat history
        setTimeout(() => {
            if (chatHistoryRef.current) {
                chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
            }
        }, 100); // Small delay to allow DOM to update
    };

    // Function to show the "Escribiendo..." loading bubble
    const showLoadingBubble = () => {
        setChatHistory((prevHistory) => [...prevHistory, { sender: 'loading', message: 'Escribiendo...' }]);
        setTimeout(() => {
            if (chatHistoryRef.current) {
                chatHistoryRef.current.scrollTop = chatHistoryRef.current.scrollHeight;
            }
        }, 100);
    };

    // Handler for sending a chat message
    const handleSendMessage = async () => {
        const message = currentMessage.trim();
        if (!message) return;

        addChatMessage(message, 'user'); // Add user's message to chat history
        setCurrentMessage(''); // Clear the input field
        showLoadingBubble(); // Show "Escribiendo..." bubble
        setIsLoading(true); // Set loading state

        try {
            const response = await fetch(`${API_BASE_URL}/chat`, { // Usa API_BASE_URL
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message }),
            });

            const data = await response.json();
            if (response.ok) {
                addChatMessage(data.response, 'ai'); // Add AI's response to chat history
            } else {
                addChatMessage(`Error al obtener respuesta: ${data.response || 'Error desconocido'}`, 'ai');
            }
        } catch (error) {
            console.error('Error al enviar mensaje al chatbot:', error);
            addChatMessage('Lo siento, no pude conectar con el chatbot.', 'ai');
        } finally {
            setIsLoading(false); // Clear loading state
            // Ensure loading bubble is removed even if there was an error
            setChatHistory((prevHistory) => {
                if (prevHistory.length > 0 && prevHistory[prevHistory.length - 1].sender === 'loading') {
                    return prevHistory.slice(0, prevHistory.length - 1);
                }
                return prevHistory;
            });
        }
    };

    // Handler for file input change (when a file is selected)
    const handleFileChange = async (event) => {
        const file = event.target.files[0];
        if (!file) {
            setStatusMessage('Ningún archivo seleccionado.');
            return;
        }

        setStatusMessage('Procesando documento... Esto puede tardar unos segundos.');
        setIsLoading(true); // Set loading state for file upload

        const formData = new FormData();
        formData.append('documento', file);

        try {
            const response = await fetch(`${API_BASE_URL}/procesar`, { // Usa API_BASE_URL
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const message = await response.text();
                setStatusMessage(`Documento procesado: ${message}`);
                addChatMessage(`Documento "${file.name}" procesado exitosamente. Ahora puedes preguntar sobre él.`, 'ai');
            } else {
                const errorText = await response.text();
                setStatusMessage(`Error al procesar: ${errorText}`);
                addChatMessage(`Error al procesar documento "${file.name}": ${errorText}`, 'ai');
            }
        } catch (error) {
            setStatusMessage(`Error de red: ${error.message}`);
            addChatMessage(`Error de red al procesar documento: ${error.message}`, 'ai');
            console.error('Error:', error);
        } finally {
            setIsLoading(false); // Clear loading state
        }
    };

    // Trigger the hidden file input click
    const handleDocumentClick = () => {
        fileInputRef.current.click();
    };

    // Suggested actions (chips) click handler
    const handleChipClick = (action) => {
        setCurrentMessage(action); // Pre-fill the input with the action
        // Optionally, send message automatically: handleSendMessage();
    };

    // Define the chips based on your PDF document
    const mainChips = [
        'Informes completo',
        'Resumen',
        'Alergias e intolerancias',
        'Medicación',
        'Curvas evolutivas',
        'Pruebas',
        'Analíticas',
        'Diagnósticos',
        'Electros',
        'Especialidades',
        'Imágenes',
        'Archivos adj.'
    ];

    return (
        <div className="flex flex-col h-screen bg-gray-900 text-white font-inter">
            {/* Top Bar - Mimicking the Meta AI UI */}
            <header className="flex items-center justify-between p-4 bg-gray-800 shadow-md">
                <button className="text-gray-400 hover:text-white transition-colors duration-200">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                </button>
                <div className="flex-1 mx-3 flex items-center bg-gray-700 rounded-full px-4 py-2 text-gray-300 text-sm">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5 mr-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                    </svg>
                    Preguntar a CliniKa AI o buscar
                </div>
                <button className="text-green-500 hover:text-green-400 transition-colors duration-200">
                    <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="currentColor" viewBox="0 0 24 24">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z"/>
                    </svg>
                </button>
            </header>

            {/* Doctor Info Section */}
            <div className="bg-gray-800 p-3 text-center text-gray-400 text-sm border-b border-gray-700">
                <p className="font-semibold text-lg">Dr. Rodolfo Gutiérrez Caro</p>
                <p className="text-sm">Especialista en Cardiología</p>
                <p className="text-xs">Colegiado 332405519</p>
            </div>

            {/* Suggested Actions / Chips (dynamically rendered from mainChips array) */}
            <div className="flex overflow-x-auto p-3 bg-gray-800 border-b border-gray-700 scrollbar-hide">
                <div className="flex space-x-2 whitespace-nowrap">
                    {mainChips.map((action, index) => (
                        <button
                            key={index}
                            onClick={() => handleChipClick(action)}
                            className="bg-gray-700 text-gray-300 px-4 py-2 rounded-full text-sm hover:bg-gray-600 focus:outline-none focus:ring-2 focus:ring-blue-500 transition-colors duration-200"
                        >
                            {action}
                        </button>
                    ))}
                </div>
            </div>

            {/* Chat History Area */}
            <main ref={chatHistoryRef} className="flex-1 overflow-y-auto p-4 bg-gray-900 scrollbar-thin scrollbar-thumb-gray-700 scrollbar-track-gray-800">
                <div className="flex flex-col space-y-3">
                    {chatHistory.map((msg, index) => (
                        <div
                            key={index}
                            className={`flex ${msg.sender === 'user' ? 'justify-end' : 'justify-start'}`}
                        >
                            {msg.sender === 'loading' ? (
                                <div className="bg-gray-700 text-gray-300 px-4 py-2 rounded-xl animate-pulse">
                                    {msg.message}
                                </div>
                            ) : (
                                <div
                                    className={`px-4 py-2 rounded-xl max-w-[80%] ${
                                        msg.sender === 'user'
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-700 text-gray-200'
                                    }`}
                                >
                                    {msg.message}
                                </div>
                            )}
                        </div>
                    ))}
                </div>
            </main>

            {/* Status Message */}
            {statusMessage && (
                <div className="p-2 text-center text-sm bg-gray-800 text-gray-400">
                    {statusMessage}
                </div>
            )}

            {/* Bottom Input and Action Buttons */}
            <footer className="p-4 bg-gray-800 border-t border-gray-700">
                <div className="flex items-center space-x-2 mb-3">
                    <input
                        type="text"
                        value={currentMessage}
                        onChange={(e) => setCurrentMessage(e.target.value)}
                        onKeyPress={(e) => {
                            if (e.key === 'Enter' && !isLoading) {
                                handleSendMessage();
                            }
                        }}
                        placeholder="Escribe tu mensaje..."
                        className="flex-1 bg-gray-700 text-white rounded-full px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-400"
                        disabled={isLoading}
                    />
                    <button
                        onClick={handleSendMessage}
                        className={`p-3 rounded-full ${isLoading ? 'bg-green-700 opacity-50 cursor-not-allowed' : 'bg-green-600 hover:bg-green-700'} text-white focus:outline-none focus:ring-2 focus:ring-green-500 transition-colors duration-200`}
                        disabled={isLoading}
                    >
                        <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6 rotate-90" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
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
