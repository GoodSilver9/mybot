#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Spotify API 통합 모듈
기존 디스코드 봇에 Spotify 기능 추가
"""

import aiohttp
import asyncio
import json
import os
from typing import Optional, List, Dict
import base64

class SpotifyAPI:
    def __init__(self):
        self.client_id = os.getenv('SPOTIFY_CLIENT_ID', '')
        self.client_secret = os.getenv('SPOTIFY_CLIENT_SECRET', '')
        self.access_token = None
        self.token_expires_at = 0
        
    async def get_access_token(self) -> bool:
        """Spotify 액세스 토큰 획득"""
        if not self.client_id or not self.client_secret:
            print("Spotify 클라이언트 ID와 시크릿이 설정되지 않았습니다.")
            return False
            
        try:
            # Basic 인증 헤더 생성
            auth_string = f"{self.client_id}:{self.client_secret}"
            auth_bytes = auth_string.encode('ascii')
            auth_b64 = base64.b64encode(auth_bytes).decode('ascii')
            
            headers = {
                'Authorization': f'Basic {auth_b64}',
                'Content-Type': 'application/x-www-form-urlencoded'
            }
            
            data = {
                'grant_type': 'client_credentials'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    'https://accounts.spotify.com/api/token',
                    headers=headers,
                    data=data
                ) as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.access_token = token_data['access_token']
                        self.token_expires_at = asyncio.get_event_loop().time() + token_data['expires_in']
                        return True
                    else:
                        print(f"토큰 획득 실패: {response.status}")
                        return False
                        
        except Exception as e:
            print(f"토큰 획득 중 오류: {e}")
            return False
    
    async def ensure_token(self) -> bool:
        """토큰이 유효한지 확인하고 필요시 갱신"""
        if not self.access_token or asyncio.get_event_loop().time() >= self.token_expires_at:
            return await self.get_access_token()
        return True
    
    async def search_tracks(self, query: str, limit: int = 10) -> List[Dict]:
        """트랙 검색"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'q': query,
                'type': 'track',
                'limit': limit,
                'market': 'KR'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/search',
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tracks = []
                        for track in data['tracks']['items']:
                            tracks.append({
                                'name': track['name'],
                                'artist': track['artists'][0]['name'],
                                'album': track['album']['name'],
                                'external_url': track['external_urls']['spotify'],
                                'preview_url': track['preview_url'],
                                'duration_ms': track['duration_ms']
                            })
                        return tracks
                    else:
                        print(f"트랙 검색 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"트랙 검색 중 오류: {e}")
            return []
    
    async def get_recommendations(self, seed_genres: List[str] = None, 
                                seed_artists: List[str] = None,
                                seed_tracks: List[str] = None,
                                target_energy: float = None,
                                target_valence: float = None,
                                limit: int = 10) -> List[Dict]:
        """음악 추천"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            params = {
                'limit': limit,
                'market': 'KR'
            }
            
            if seed_genres:
                params['seed_genres'] = ','.join(seed_genres[:5])
            if seed_artists:
                params['seed_artists'] = ','.join(seed_artists[:5])
            if seed_tracks:
                params['seed_tracks'] = ','.join(seed_tracks[:5])
            if target_energy is not None:
                params['target_energy'] = target_energy
            if target_valence is not None:
                params['target_valence'] = target_valence
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/recommendations',
                    headers=headers,
                    params=params
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        tracks = []
                        for track in data['tracks']:
                            tracks.append({
                                'name': track['name'],
                                'artist': track['artists'][0]['name'],
                                'album': track['album']['name'],
                                'external_url': track['external_urls']['spotify'],
                                'preview_url': track['preview_url'],
                                'duration_ms': track['duration_ms']
                            })
                        return tracks
                    else:
                        print(f"추천 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"추천 중 오류: {e}")
            return []
    
    async def get_available_genres(self) -> List[str]:
        """사용 가능한 장르 목록 가져오기"""
        if not await self.ensure_token():
            return []
            
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    'https://api.spotify.com/v1/recommendations/available-genre-seeds',
                    headers=headers
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data['genres']
                    else:
                        print(f"장르 목록 가져오기 실패: {response.status}")
                        return []
                        
        except Exception as e:
            print(f"장르 목록 가져오기 중 오류: {e}")
            return []

# 감정 분석을 위한 간단한 키워드 매핑
EMOTION_KEYWORDS = {
    '기쁨': {'energy': 0.8, 'valence': 0.8, 'genres': ['pop', 'dance']},
    '슬픔': {'energy': 0.3, 'valence': 0.2, 'genres': ['sad', 'acoustic']},
    '화남': {'energy': 0.7, 'valence': 0.3, 'genres': ['rock', 'metal']},
    '평온': {'energy': 0.4, 'valence': 0.6, 'genres': ['ambient', 'chill']},
    '신남': {'energy': 0.9, 'valence': 0.9, 'genres': ['edm', 'dance']},
    '잔잔': {'energy': 0.2, 'valence': 0.5, 'genres': ['acoustic', 'folk']},
    '활기': {'energy': 0.8, 'valence': 0.7, 'genres': ['pop', 'funk']},
    '힘듦': {'energy': 0.4, 'valence': 0.3, 'genres': ['indie', 'alternative']}
}

async def analyze_emotion_and_recommend(text: str, spotify_api: SpotifyAPI) -> List[Dict]:
    """텍스트에서 감정을 분석하고 Spotify 추천"""
    text_lower = text.lower()
    
    # 감정 키워드 매칭
    matched_emotion = None
    for emotion, keywords in EMOTION_KEYWORDS.items():
        if emotion in text_lower or any(keyword in text_lower for keyword in ['기쁘', '슬프', '화나', '평온', '신나', '잔잔', '활기', '힘들']):
            matched_emotion = emotion
            break
    
    if matched_emotion:
        emotion_config = EMOTION_KEYWORDS[matched_emotion]
        recommendations = await spotify_api.get_recommendations(
            seed_genres=emotion_config['genres'],
            target_energy=emotion_config['energy'],
            target_valence=emotion_config['valence'],
            limit=5
        )
        return recommendations
    else:
        # 기본 추천
        return await spotify_api.get_recommendations(
            seed_genres=['pop'],
            limit=5
        )

# 전역 Spotify API 인스턴스
spotify_api = SpotifyAPI() 