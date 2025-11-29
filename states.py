from aiogram.fsm.state import State, StatesGroup

class VideoNoteState(StatesGroup):
    waiting_for_video = State()